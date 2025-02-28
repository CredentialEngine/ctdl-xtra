
export * from './base';
export * from './coursedog';

import { ApiProvider } from '@common/types';
import { CourseDogAPIService } from './coursedog';

export const apiExtractorServices = {
  [ApiProvider.Coursedog]: new CourseDogAPIService()
}