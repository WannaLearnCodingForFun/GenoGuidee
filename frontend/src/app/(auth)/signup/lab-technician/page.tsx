"use client";

import { useState } from "react";
import { SignupForm, fieldLabelClass, fieldInputClass } from "../SignupForm";

export default function LabTechnicianSignupPage() {
  const [labName, setLabName] = useState("");
  const [certificationId, setCertificationId] = useState("");

  return (
    <SignupForm
      role="lab_technician"
      buildMetadata={() => ({
        lab_name: labName,
        ...(certificationId ? { certification_id: certificationId } : {}),
      })}
      extraFields={
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={fieldLabelClass}>Lab name</label>
            <input
              required
              value={labName}
              onChange={(e) => setLabName(e.target.value)}
              className={fieldInputClass}
            />
          </div>
          <div>
            <label className={fieldLabelClass}>Certification ID</label>
            <input
              value={certificationId}
              onChange={(e) => setCertificationId(e.target.value)}
              className={fieldInputClass}
            />
          </div>
        </div>
      }
    />
  );
}
