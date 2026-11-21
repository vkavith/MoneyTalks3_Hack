// LANE 1. STUB: returns the ground-truth fixture instead of reading the PDF.
// Replace the body with real extraction. Keep the signature.
import type { CaptureStage } from "@ap/shared";
import { loadCapturedFixture } from "@ap/shared/load";

export const capture: CaptureStage = async (sourceFile) => {
  return loadCapturedFixture(sourceFile);
};
