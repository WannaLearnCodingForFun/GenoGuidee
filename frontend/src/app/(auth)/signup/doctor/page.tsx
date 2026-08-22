"use client";

import { useState } from "react";
import { SignupForm, fieldLabelClass, fieldInputClass } from "../SignupForm";

export default function DoctorSignupPage() {
  const [licenseNumber, setLicenseNumber] = useState("");
  const [specialty, setSpecialty] = useState("");

  return (
    <SignupForm
      role="doctor"
      buildMetadata={() => ({
        license_number: licenseNumber,
        ...(specialty ? { specialty } : {}),
      })}
      extraFields={
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={fieldLabelClass}>License number</label>
            <input
              required
              value={licenseNumber}
              onChange={(e) => setLicenseNumber(e.target.value)}
              className={fieldInputClass}
            />
          </div>
          <div>
            <label className={fieldLabelClass}>Specialty</label>
            <input
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              className={fieldInputClass}
              placeholder="Clinical genetics"
            />
          </div>
        </div>
      }
    />
  );
}
