import profileDocument from "./classifier-profile.generated.json";

import type { Accent, ClassifierProfile } from "../types";

type GeneratedProfileDocument = {
  schema_version: number;
  source: string;
  source_hash: string;
  corpus_complete: boolean;
  missing_target_ids: string[];
  profiles: Record<Accent, ClassifierProfile>;
};

const generated = profileDocument as GeneratedProfileDocument;

export const CLASSIFIER_PROFILE_SCHEMA_VERSION = generated.schema_version;
export const CLASSIFIER_PROFILE_SOURCE = generated.source;
export const CLASSIFIER_PROFILE_SOURCE_HASH = generated.source_hash;
export const CLASSIFIER_CORPUS_COMPLETE = generated.corpus_complete;
export const CLASSIFIER_MISSING_TARGET_IDS = Object.freeze([
  ...generated.missing_target_ids,
]);

export function staticClassifierProfile(accent: Accent): ClassifierProfile {
  return generated.profiles[accent];
}
