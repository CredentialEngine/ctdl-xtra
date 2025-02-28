import { registerProbes } from './base';
import { CourseDog } from './coursedog';

export const Probes = registerProbes([
  new CourseDog(),
]);