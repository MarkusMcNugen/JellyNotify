import { useState } from 'react';
import { Icon } from './FontAwesomeIcon';

const Tooltip = ({ text, position = 'top' }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const getPositionClasses = () => {
    switch (position) {
      case 'top':
        return 'bottom-full left-1/2 transform -translate-x-1/2 mb-2';
      case 'bottom':
        return 'top-full left-1/2 transform -translate-x-1/2 mt-2';
      case 'left':
        return 'right-full top-1/2 transform -translate-y-1/2 mr-2';
      case 'right':
        return 'left-full top-1/2 transform -translate-y-1/2 ml-2';
      default:
        return 'bottom-full left-1/2 transform -translate-x-1/2 mb-2';
    }
  };

  const getArrowClasses = () => {
    switch (position) {
      case 'top':
        return 'top-full left-1/2 transform -translate-x-1/2 border-gray-900 dark:border-gray-700 border-t-8 border-x-4 border-x-transparent';
      case 'bottom':
        return 'bottom-full left-1/2 transform -translate-x-1/2 border-gray-900 dark:border-gray-700 border-b-8 border-x-4 border-x-transparent';
      case 'left':
        return 'left-full top-1/2 transform -translate-y-1/2 border-gray-900 dark:border-gray-700 border-l-8 border-y-4 border-y-transparent';
      case 'right':
        return 'right-full top-1/2 transform -translate-y-1/2 border-gray-900 dark:border-gray-700 border-r-8 border-y-4 border-y-transparent';
      default:
        return 'top-full left-1/2 transform -translate-x-1/2 border-gray-900 dark:border-gray-700 border-t-8 border-x-4 border-x-transparent';
    }
  };

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="inline-flex items-center justify-center w-4 h-4 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 cursor-help"
      >
        <Icon icon="info-circle" size="sm" />
      </div>
      
      {showTooltip && (
        <div className={`absolute z-50 ${getPositionClasses()} pointer-events-none`}>
          <div className="relative">
            <div className="bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg py-2 px-3 max-w-md whitespace-normal leading-relaxed">
              {text}
            </div>
            <div className={`absolute ${getArrowClasses()}`} />
          </div>
        </div>
      )}
    </div>
  );
};

export default Tooltip;