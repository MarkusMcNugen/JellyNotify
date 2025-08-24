#!/usr/bin/env python3
"""
SSL/TLS Certificate Management Module for Jellynouncer

This module provides comprehensive SSL/TLS certificate management including:
- Support for PFX/PKCS12 and PEM certificate formats
- Certificate validation and information extraction
- CSR (Certificate Signing Request) generation
- Private key generation and management
- Certificate chain validation

Security Features:
    - Secure key generation with configurable key sizes
    - Certificate validation before use
    - Safe storage of certificate configurations
    - Support for password-protected PFX files

Author: Mark Newton
Project: Jellynouncer
Version: 1.0.0
License: MIT
"""

import os
import ssl
import socket
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
import aiosqlite

from .utils import get_logger


class SSLManager:
    """
    Manages SSL/TLS certificates for secure communications.
    
    This class handles all aspects of SSL certificate management including
    loading, validation, generation, and configuration. It supports both
    PFX and PEM formats and provides utilities for CSR generation.
    """
    
    def __init__(self, db_path: str = "data/web_interface.db", ssl_config=None):
        """
        Initialize SSL Manager.
        
        Args:
            db_path: Database path for SSL settings and CSR tracking
            ssl_config: Initial SSLConfig object from config.json
        """
        self.logger = get_logger("ssl_manager")
        self.db_path = db_path
        self.initial_ssl_config = ssl_config  # Initial config from config.json
        self.cert_dir = Path("data/certificates")
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
    async def initialize(self):
        """Initialize SSL settings in database"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ssl_settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    ssl_enabled BOOLEAN DEFAULT 0,
                    cert_type TEXT,  -- 'pem' or 'pfx'
                    cert_path TEXT,
                    key_path TEXT,  -- for PEM only
                    chain_path TEXT,  -- optional chain for PEM
                    pfx_password TEXT,  -- encrypted password for PFX
                    port INTEGER DEFAULT 9000,
                    force_https BOOLEAN DEFAULT 0,
                    hsts_enabled BOOLEAN DEFAULT 0,
                    hsts_max_age INTEGER DEFAULT 31536000,
                    config_hash TEXT,  -- Hash of config.json settings to detect changes
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK (id = 1)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS csr_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    common_name TEXT NOT NULL,
                    organization TEXT,
                    organizational_unit TEXT,
                    locality TEXT,
                    state TEXT,
                    country TEXT,
                    email TEXT,
                    key_size INTEGER DEFAULT 2048,
                    csr_path TEXT,
                    key_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.commit()
            
            # Initialize default SSL settings if not exists
            cursor = await db.execute("SELECT COUNT(*) FROM ssl_settings")
            if (await cursor.fetchone())[0] == 0:
                await db.execute("""
                    INSERT INTO ssl_settings (ssl_enabled, force_https, hsts_enabled) 
                    VALUES (0, 0, 0)
                """)
                await db.commit()
            
            # Sync config.json to database if changed
            await self._sync_config_to_db()
    
    async def get_ssl_settings(self) -> Dict[str, Any]:
        """Get current SSL configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM ssl_settings WHERE id = 1")
            settings = await cursor.fetchone()
            
            if settings:
                return dict(settings)
            return {
                "ssl_enabled": False,
                "cert_type": None,
                "port": 9000
            }
    
    async def update_ssl_settings(self, settings: Dict[str, Any]) -> bool:
        """Update SSL configuration in database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE ssl_settings 
                    SET ssl_enabled = ?, cert_type = ?, cert_path = ?, 
                        key_path = ?, chain_path = ?, pfx_password = ?,
                        port = ?, force_https = ?, hsts_enabled = ?, 
                        hsts_max_age = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (
                    settings.get("ssl_enabled", False),
                    settings.get("cert_type"),
                    settings.get("cert_path"),
                    settings.get("key_path"),
                    settings.get("chain_path"),
                    settings.get("pfx_password"),
                    settings.get("port", 9000),
                    settings.get("force_https", False),
                    settings.get("hsts_enabled", False),
                    settings.get("hsts_max_age", 31536000)
                ))
                await db.commit()
                self.logger.info("SSL settings updated successfully")
                return True
        except Exception as e:
            self.logger.error(f"Failed to update SSL settings: {e}")
            return False
    
    @staticmethod
    def generate_private_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
        """Generate a new RSA private key"""
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
    
    @staticmethod
    def generate_csr(
        private_key: rsa.RSAPrivateKey,
        common_name: str,
        organization: Optional[str] = None,
        organizational_unit: Optional[str] = None,
        locality: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        email: Optional[str] = None,
        san_list: Optional[List[str]] = None
    ) -> x509.CertificateSigningRequest:
        """
        Generate a Certificate Signing Request (CSR)
        
        Args:
            private_key: The private key to use
            common_name: The domain name (CN)
            organization: Organization name (O)
            organizational_unit: Department (OU)
            locality: City (L)
            state: State or Province (ST)
            country: Country code (C) - must be 2 letters
            email: Email address
            san_list: List of Subject Alternative Names
        
        Returns:
            The generated CSR
        """
        # Build subject
        subject_components = [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
        
        if organization:
            subject_components.append(
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization)
            )
        if organizational_unit:
            subject_components.append(
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organizational_unit)
            )
        if locality:
            subject_components.append(
                x509.NameAttribute(NameOID.LOCALITY_NAME, locality)
            )
        if state:
            subject_components.append(
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state)
            )
        if country and len(country) == 2:
            subject_components.append(
                x509.NameAttribute(NameOID.COUNTRY_NAME, country.upper())
            )
        if email:
            subject_components.append(
                x509.NameAttribute(NameOID.EMAIL_ADDRESS, email)
            )
        
        subject = x509.Name(subject_components)
        
        # Create CSR builder
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(subject)
        
        # Add Subject Alternative Names if provided
        if san_list:
            san_names = []
            for san in san_list:
                if san.startswith("*."):
                    # Wildcard domain
                    san_names.append(x509.DNSName(san))
                elif "@" in san:
                    # Email address
                    san_names.append(x509.RFC822Name(san))
                elif san.replace(".", "").isdigit():
                    # IP address
                    import ipaddress
                    san_names.append(x509.IPAddress(ipaddress.ip_address(san)))
                else:
                    # Regular domain
                    san_names.append(x509.DNSName(san))
            
            if san_names:
                builder = builder.add_extension(
                    x509.SubjectAlternativeName(san_names),
                    critical=False,
                )
        
        # Sign the CSR
        csr = builder.sign(private_key, hashes.SHA256(), backend=default_backend())
        
        return csr
    
    async def create_csr_request(
        self,
        common_name: str,
        organization: Optional[str] = None,
        organizational_unit: Optional[str] = None,
        locality: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        email: Optional[str] = None,
        key_size: int = 2048,
        san_list: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Create a new CSR and save it to disk
        
        Returns:
            Dictionary with paths to the CSR and private key files
        """
        try:
            # Generate private key
            private_key = self.generate_private_key(key_size)
            
            # Generate CSR
            csr = self.generate_csr(
                private_key,
                common_name,
                organization,
                organizational_unit,
                locality,
                state,
                country,
                email,
                san_list
            )
            
            # Generate unique filenames
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_cn = common_name.replace("*", "wildcard").replace(".", "_")
            
            csr_filename = f"csr_{safe_cn}_{timestamp}.pem"
            key_filename = f"key_{safe_cn}_{timestamp}.pem"
            
            csr_path = self.cert_dir / csr_filename
            key_path = self.cert_dir / key_filename
            
            # Save CSR
            with open(csr_path, "wb") as f:
                f.write(csr.public_bytes(serialization.Encoding.PEM))
            
            # Save private key (encrypted with a generated password)
            key_password = secrets.token_urlsafe(32)
            with open(key_path, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.BestAvailableEncryption(
                        key_password.encode()
                    )
                ))
            
            # Save to database
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO csr_requests 
                    (common_name, organization, organizational_unit, locality, 
                     state, country, email, key_size, csr_path, key_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    common_name, organization, organizational_unit, locality,
                    state, country, email, key_size, str(csr_path), str(key_path)
                ))
                await db.commit()
                csr_id = cursor.lastrowid
            
            self.logger.info(f"Created CSR for {common_name}")
            
            return {
                "csr_id": csr_id,
                "csr_path": str(csr_path),
                "key_path": str(key_path),
                "key_password": key_password,
                "csr_content": csr.public_bytes(serialization.Encoding.PEM).decode()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create CSR: {e}")
            raise
    
    def validate_certificate(self, cert_path: str) -> Dict[str, Any]:
        """
        Validate and extract information from a certificate
        
        Returns:
            Dictionary with certificate information
        """
        try:
            with open(cert_path, "rb") as f:
                cert_data = f.read()
            
            # Try to load as PEM first
            try:
                cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            except:
                # Try DER format
                cert = x509.load_der_x509_certificate(cert_data, default_backend())
            
            # Extract certificate information
            info = {
                "valid": True,
                "subject": {
                    "common_name": None,
                    "organization": None,
                    "country": None
                },
                "issuer": {
                    "common_name": None,
                    "organization": None
                },
                "serial_number": str(cert.serial_number),
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "signature_algorithm": cert.signature_algorithm_oid._name,
                "san_list": [],
                "is_self_signed": cert.issuer == cert.subject
            }
            
            # Extract subject information
            for attribute in cert.subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    info["subject"]["common_name"] = str(attribute.value)
                elif attribute.oid == NameOID.ORGANIZATION_NAME:
                    info["subject"]["organization"] = str(attribute.value)
                elif attribute.oid == NameOID.COUNTRY_NAME:
                    info["subject"]["country"] = str(attribute.value)
            
            # Extract issuer information
            for attribute in cert.issuer:
                if attribute.oid == NameOID.COMMON_NAME:
                    info["issuer"]["common_name"] = str(attribute.value)
                elif attribute.oid == NameOID.ORGANIZATION_NAME:
                    info["issuer"]["organization"] = str(attribute.value)
            
            # Extract SANs
            try:
                san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for san in san_ext.value:
                    info["san_list"].append(str(san.value))
            except x509.ExtensionNotFound:
                pass
            
            # Check if certificate is expired
            now = datetime.now(timezone.utc)
            if now < cert.not_valid_before or now > cert.not_valid_after:
                info["valid"] = False
                info["error"] = "Certificate is expired or not yet valid"
            
            return info
            
        except Exception as e:
            self.logger.error(f"Failed to validate certificate: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    def validate_pfx(self, pfx_path: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate and extract information from a PFX/PKCS12 file
        
        Returns:
            Dictionary with certificate information
        """
        try:
            with open(pfx_path, "rb") as f:
                pfx_data = f.read()
            
            # Load PFX
            pfx_password = password.encode() if password else None
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                pfx_data,
                pfx_password,
                backend=default_backend()
            )
            
            if not certificate:
                return {
                    "valid": False,
                    "error": "No certificate found in PFX file"
                }
            
            # Get certificate info
            info = {
                "valid": True,
                "has_private_key": private_key is not None,
                "subject": {
                    "common_name": None,
                    "organization": None
                },
                "not_before": certificate.not_valid_before.isoformat(),
                "not_after": certificate.not_valid_after.isoformat(),
                "chain_count": len(additional_certs) if additional_certs else 0
            }
            
            # Extract subject information
            for attribute in certificate.subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    info["subject"]["common_name"] = str(attribute.value)
                elif attribute.oid == NameOID.ORGANIZATION_NAME:
                    info["subject"]["organization"] = str(attribute.value)
            
            # Check expiration
            now = datetime.now(timezone.utc)
            if now < certificate.not_valid_before or now > certificate.not_valid_after:
                info["valid"] = False
                info["error"] = "Certificate is expired or not yet valid"
            
            return info
            
        except Exception as e:
            self.logger.error(f"Failed to validate PFX: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    def create_ssl_context(self, settings: Dict[str, Any]) -> Optional[ssl.SSLContext]:
        """
        Create an SSL context from the provided settings
        
        Returns:
            Configured SSL context or None if SSL is disabled
        """
        # Check for both 'enabled' (new config) and 'ssl_enabled' (legacy)
        if not settings.get("enabled") and not settings.get("ssl_enabled"):
            return None
        
        try:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            
            cert_type = settings.get("cert_type")
            
            if cert_type == "pem":
                # Load PEM certificate and key
                cert_path = settings.get("cert_path")
                key_path = settings.get("key_path")
                chain_path = settings.get("chain_path")
                
                if not cert_path or not key_path:
                    self.logger.error("Certificate or key path not provided")
                    return None
                
                # Load certificate chain if provided
                if chain_path and os.path.exists(chain_path):
                    context.load_cert_chain(cert_path, key_path, chain_path)
                else:
                    context.load_cert_chain(cert_path, key_path)
                    
            elif cert_type == "pfx":
                # Load PFX certificate
                pfx_path = settings.get("cert_path")
                pfx_password = settings.get("pfx_password")
                
                if not pfx_path:
                    self.logger.error("PFX path not provided")
                    return None
                
                # Convert PFX to PEM format temporarily
                with open(pfx_path, "rb") as f:
                    pfx_data = f.read()
                
                pfx_password_bytes = pfx_password.encode() if pfx_password else None
                private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                    pfx_data,
                    pfx_password_bytes,
                    backend=default_backend()
                )
                
                # Create temporary PEM files
                temp_cert = self.cert_dir / f"temp_cert_{os.getpid()}.pem"
                temp_key = self.cert_dir / f"temp_key_{os.getpid()}.pem"
                
                try:
                    # Write certificate
                    with open(temp_cert, "wb") as f:
                        f.write(certificate.public_bytes(serialization.Encoding.PEM))
                        # Add chain certificates if present
                        if additional_certs:
                            for cert in additional_certs:
                                f.write(cert.public_bytes(serialization.Encoding.PEM))
                    
                    # Write private key
                    with open(temp_key, "wb") as f:
                        f.write(private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.TraditionalOpenSSL,
                            encryption_algorithm=serialization.NoEncryption()
                        ))
                    
                    # Load into context
                    context.load_cert_chain(str(temp_cert), str(temp_key))
                    
                finally:
                    # Clean up temporary files
                    if temp_cert.exists():
                        temp_cert.unlink()
                    if temp_key.exists():
                        temp_key.unlink()
            
            else:
                self.logger.error(f"Unknown certificate type: {cert_type}")
                return None
            
            # Configure SSL options
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
            
            self.logger.info("SSL context created successfully")
            return context
            
        except Exception as e:
            self.logger.error(f"Failed to create SSL context: {e}")
            return None
    
    async def _sync_config_to_db(self):
        """Sync config.json SSL settings to database if changed."""
        if not self.initial_ssl_config:
            return
            
        try:
            # Calculate hash of config settings
            import hashlib
            import json
            config_dict = self.initial_ssl_config.model_dump() if hasattr(self.initial_ssl_config, 'model_dump') else {}
            if config_dict:
                config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()
                
                async with aiosqlite.connect(self.db_path) as db:
                    # Check if settings exist and if config has changed
                    cursor = await db.execute("SELECT config_hash FROM ssl_settings WHERE id = 1")
                    row = await cursor.fetchone()
                    
                    if not row:
                        # First time - insert settings from config
                        await db.execute("""
                            INSERT INTO ssl_settings (
                                ssl_enabled, cert_type, cert_path, key_path, chain_path,
                                pfx_password, port, force_https, hsts_enabled, hsts_max_age, config_hash
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            config_dict.get("enabled", False),
                            config_dict.get("cert_type"),
                            config_dict.get("cert_path"),
                            config_dict.get("key_path"),
                            config_dict.get("chain_path"),
                            config_dict.get("pfx_password"),
                            config_dict.get("port", 9000),
                            config_dict.get("force_https", False),
                            config_dict.get("hsts_enabled", False),
                            config_dict.get("hsts_max_age", 31536000),
                            config_hash
                        ))
                        await db.commit()
                        self.logger.info("Initialized SSL settings from config.json")
                    elif row[0] != config_hash:
                        # Config has changed - update database
                        await db.execute("""
                            UPDATE ssl_settings 
                            SET ssl_enabled = ?, cert_type = ?, cert_path = ?, 
                                key_path = ?, chain_path = ?, pfx_password = ?,
                                port = ?, force_https = ?, hsts_enabled = ?, 
                                hsts_max_age = ?, config_hash = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = 1
                        """, (
                            config_dict.get("enabled", False),
                            config_dict.get("cert_type"),
                            config_dict.get("cert_path"),
                            config_dict.get("key_path"),
                            config_dict.get("chain_path"),
                            config_dict.get("pfx_password"),
                            config_dict.get("port", 9000),
                            config_dict.get("force_https", False),
                            config_dict.get("hsts_enabled", False),
                            config_dict.get("hsts_max_age", 31536000),
                            config_hash
                        ))
                        await db.commit()
                        self.logger.info("Updated SSL settings from config.json (config changed)")
                    else:
                        self.logger.debug("SSL settings unchanged in config.json")
                        
        except Exception as e:
            self.logger.error(f"Failed to sync config to database: {e}")
            # Don't fail initialization if sync fails
    
    async def test_ssl_configuration(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test SSL configuration by creating a test server
        
        Returns:
            Dictionary with test results
        """
        context = self.create_ssl_context(settings)
        
        if not context:
            return {
                "success": False,
                "error": "Failed to create SSL context"
            }
        
        try:
            # Create a test server socket
            test_port = settings.get("port", 9000)
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', test_port))
                sock.listen(5)
                
                with context.wrap_socket(sock, server_side=True):
                    # If we get here, SSL is configured correctly
                    return {
                        "success": True,
                        "message": f"SSL configuration valid, test server created on port {test_port}"
                    }
                    
        except OSError as e:
            if "Address already in use" in str(e):
                return {
                    "success": True,
                    "message": "SSL configuration appears valid (port in use)"
                }
            return {
                "success": False,
                "error": f"SSL configuration error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"SSL test failed: {str(e)}"
            }


# Utility functions for web API integration

async def setup_ssl_routes(app, ssl_manager: SSLManager):
    """Add SSL management routes to FastAPI app"""
    from fastapi import HTTPException, UploadFile, File, Form
    from pydantic import BaseModel
    
    class CSRRequest(BaseModel):
        common_name: str
        organization: Optional[str] = None
        organizational_unit: Optional[str] = None
        locality: Optional[str] = None
        state: Optional[str] = None
        country: Optional[str] = None
        email: Optional[str] = None
        key_size: int = 2048
        san_list: Optional[List[str]] = None
    
    class SSLSettings(BaseModel):
        ssl_enabled: bool
        cert_type: Optional[str] = None
        port: int = 9000
        force_https: bool = False
        hsts_enabled: bool = False
        hsts_max_age: int = 31536000
    
    @app.get("/api/ssl/settings")
    async def get_ssl_settings():
        """Get current SSL settings"""
        return await ssl_manager.get_ssl_settings()
    
    @app.put("/api/ssl/settings")
    async def update_ssl_settings(settings: SSLSettings):
        """Update SSL settings"""
        settings_dict = settings.model_dump()
        success = await ssl_manager.update_ssl_settings(settings_dict)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update SSL settings")
        
        return {"message": "SSL settings updated"}
    
    @app.post("/api/ssl/csr")
    async def generate_csr(request: CSRRequest):
        """Generate a new Certificate Signing Request"""
        try:
            result = await ssl_manager.create_csr_request(
                common_name=request.common_name,
                organization=request.organization,
                organizational_unit=request.organizational_unit,
                locality=request.locality,
                state=request.state,
                country=request.country,
                email=request.email,
                key_size=request.key_size,
                san_list=request.san_list
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/ssl/upload-cert")
    async def upload_certificate(
        file: UploadFile = File(...),
        cert_type: str = Form(...),
        password: Optional[str] = Form(None)
    ):
        """Upload and validate a certificate"""
        # Save uploaded file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"cert_{timestamp}_{file.filename}"
        file_path = ssl_manager.cert_dir / filename
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Validate certificate
        if cert_type == "pfx":
            info = ssl_manager.validate_pfx(str(file_path), password)
        else:
            info = ssl_manager.validate_certificate(str(file_path))
        
        if not info["valid"]:
            file_path.unlink()  # Delete invalid certificate
            raise HTTPException(status_code=400, detail=info.get("error", "Invalid certificate"))
        
        info["file_path"] = str(file_path)
        return info
    
    @app.post("/api/ssl/test")
    async def test_ssl_config():
        """Test current SSL configuration"""
        settings = await ssl_manager.get_ssl_settings()
        result = await ssl_manager.test_ssl_configuration(settings)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result