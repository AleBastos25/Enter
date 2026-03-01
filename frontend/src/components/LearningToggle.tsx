/** Toggle para aprendizado incremental. */

"use client";

import { useState, useEffect } from "react";
import { storage } from "@/lib/storage";

interface LearningToggleProps {
  value?: boolean;
  onChange?: (enabled: boolean) => void;
}

export function LearningToggle({ value, onChange }: LearningToggleProps) {
  const [enabled, setEnabled] = useState(value ?? true);

  useEffect(() => {
    if (value === undefined) {
      setEnabled(storage.loadUseLearning() ?? true);
    } else {
      setEnabled(value);
    }
  }, [value]);

  const handleToggle = () => {
    const newValue = !enabled;
    setEnabled(newValue);
    storage.saveUseLearning(newValue);
    if (onChange) {
      onChange(newValue);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={handleToggle}
          className="sr-only"
        />
        <div
          className={`relative w-11 h-6 rounded-full transition-colors ${
            enabled ? "bg-[#4CAF50]" : "bg-[#404040]"
          }`}
        >
          <div
            className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
              enabled ? "translate-x-5" : ""
            }`}
          />
        </div>
        <span className="ml-2 text-sm font-medium text-[#e5e5e5]">Learning</span>
      </label>
    </div>
  );
}

