"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function GenomicTimelineByPatient() {
  const params = useParams<{ patientId: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/genomic-timeline?patient=${params.patientId}`);
  }, [params.patientId, router]);
  return <p className="px-8 py-8 text-sm text-muted">Opening genomic timeline…</p>;
}
