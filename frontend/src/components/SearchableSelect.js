import React, { useState, useRef, useEffect } from 'react';

function SearchableSelect({ options, value, onChange, placeholder, formatOption, formatSelected }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const filtered = search
    ? options.filter(o => {
        // Search against the plain text label, not the JSX formatted version
        const text = (o.label + ' ' + (o.extra || '') + ' ' + (o.value || '')).toLowerCase();
        return text.includes(search.toLowerCase());
      })
    : options;

  const selectedOption = options.find(o => o.value === value);

  return (
    <div className="searchable-select" ref={ref}>
      <div
        className={`ss-trigger ${open ? 'open' : ''} ${value ? 'has-value' : ''}`}
        onClick={() => { setOpen(!open); setSearch(''); }}
      >
        {value && selectedOption
          ? (formatSelected ? formatSelected(selectedOption) : selectedOption.label)
          : <span className="ss-placeholder">{placeholder}</span>
        }
        <span className="ss-arrow">&#9662;</span>
      </div>
      {open && (
        <div className="ss-dropdown">
          <input
            type="text"
            className="ss-search"
            placeholder="Type to search..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
          <div className="ss-options">
            {filtered.length === 0 && (
              <div className="ss-no-results">No matches</div>
            )}
            {filtered.slice(0, 30).map(o => (
              <div
                key={o.value}
                className={`ss-option ${o.value === value ? 'selected' : ''}`}
                onClick={() => { onChange(o.value); setOpen(false); setSearch(''); }}
              >
                {formatOption ? formatOption(o) : o.label}
              </div>
            ))}
            {filtered.length > 30 && (
              <div className="ss-more">Type to narrow down ({filtered.length - 30} more)</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default SearchableSelect;
