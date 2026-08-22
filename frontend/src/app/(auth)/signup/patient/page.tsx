"use client";

import { useState } from "react";
import { SignupForm, fieldLabelClass, fieldInputClass } from "../SignupForm";

export default function PatientSignupPage() {
  const [dateOfBirth, setDateOfBirth] = useState("");

  return (
    <SignupForm
      role="patient"
      buildMetadata={() => (dateOfBirth ? ({ date_of_birth: dateOfBirth } as Record<string, string>) : {})}
      extraFields={
        <div>
          <label className={fieldLabelClass}>Date of birth</label>
          <input
            type="date"
            value={dateOfBirth}
            onChange={(e) => setDateOfBirth(e.target.value)}
            className={fieldInputClass}
          />
        </div>
      }
    />
  );
}
