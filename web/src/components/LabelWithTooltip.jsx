import Tooltip from './Tooltip';

const LabelWithTooltip = ({ label, tooltip, htmlFor, className = "" }) => {
  return (
    <label 
      htmlFor={htmlFor}
      className={`flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 ${className}`}
    >
      <span>{label}</span>
      {tooltip && <Tooltip text={tooltip} />}
    </label>
  );
};

export default LabelWithTooltip;