import { exponentialRetry } from '@/utils';
import querystring from 'node:querystring';
import { VendorExtractionService } from './base';
import { Recipe } from '@/data/recipes';
import { CourseStructuredData } from '@common/types';

export class CourseDogAPIService extends VendorExtractionService {
  apiBase = "https://app.coursedog.com/api/v1";

  public async extractData(recipe: Recipe, onResultBatch: (res: CourseStructuredData[]) => Promise<boolean>): Promise<void>  {
    // @ts-ignore
    let { schoolId, catalogIds } = recipe.configuration?.apiConfig || {}; 
    if (!schoolId) { 
      throw new Error(`Coursedog schoolId is required to retrieve course information.`);
    }

    const allCatalogs = await this.getCatalogs(schoolId);
    const targetedCatalogs = Array.isArray(catalogIds)
      ? allCatalogs.filter(entry => catalogIds.includes(entry.id))
      : allCatalogs;
    
    
    for (const catalog of targetedCatalogs) {
      await this.getAllCatalogCourses(
        schoolId,
        catalog,
        function onData(response) {
          let courses: CourseStructuredData[] = response.data.map(
            cgCourse => ({
              course_id: cgCourse.id,
              course_description: cgCourse.description,
              course_name: cgCourse.longName,
              course_credits_min: cgCourse.credits.creditHours.min,
            })
          );

          return onResultBatch(courses)
        }
      );
    }
  }

  public async getCatalogs(schoolId: string): Promise<CourseDogCatalog[]> {
    return fetch(`${this.apiBase}/ca/${schoolId}/catalogs`)
      .then(r => r.json() as Promise<CourseDogCatalog[]>)
  }

  /**
   * Iterates all pages containing courses for the given school ID and
   * catalog with a limit of up 20 courses per page. The calls are 
   * done in sequence and are exponentially retried in case of failure.
   * 
   * @param schoolId 
   * @param catalog 
   */
  public async getAllCatalogCourses(
    schoolId: string,
    catalog: CourseDogCatalog,
    onBatch: (results: CourseSearchApiResponse) => Promise<boolean>
  ) {
    const url = `${this.apiBase}/cm/${schoolId}/courses/search/%24filters`;
    const parameters = {
      catalogId: catalog.id,
      skip: 0,
      limit: 20,
      orderBy: [
        'catalogDisplayName',
        'transcriptDescription',
        'longName',
        'name'
      ].join(','),
      formatDependents: 'false',
      effectiveDatesRange: [
        catalog.effectiveStartDate,
        catalog.effectiveEndDate
      ].join(','),
      columns: [
        'customFields.rawCourseId',
        'customFields.crseOfferNbr',
        'customFields.catalogAttributes',
        'displayName',
        'department',
        'description',
        'name',
        'courseNumber',
        'subjectCode',
        'code',
        'courseGroupId',
        'career',
        'college',
        'longName',
        'status',
        'institution',
        'institutionId',
        'credits'
      ].join(',')
    }

    if (!catalog.effectiveEndDate || !catalog.effectiveStartDate) {
      // @ts-expect-error ts(2790)
      delete parameters.effectiveDatesRange;
    }

    const limit = 20;
    let numCalls = 1;
    let listLength = 0;

    for (let i = 0; i < numCalls; i++) {
      const skipValue = i * limit;
      const query = querystring.stringify({...parameters, skip: String(skipValue)});
      const pageUrl = `${url}?${query}`;
      const response = await exponentialRetry(
        () => fetch(pageUrl).then(r => r.json() as Promise<CourseSearchApiResponse>),
        10,
        10 * 1000,
      );

      listLength = response.listLength;
      numCalls = Math.ceil(listLength / limit);

      if (!await onBatch(response)) {
        break;
      }
    }
  }
}

//#region Types
export interface CourseDogCatalog {
  sidebar: any[]
  displayName: string
  effectiveStartDate: string
  websiteSettings: Record<any, any>
  createdAt: number
  createdBy: string
  lastEditedAt: number
  lastEditedBy: string
  id: string
  coursesFilters: CoursesFilters
  departmentsFilters: DepartmentsFilters
  effectiveEndDate: string
  instructorsFilters: InstructorsFilters
  programsFilters: ProgramsFilters
  coursePageTemplateId: string
  programPageTemplateId: string
  courseSearchConfigurationId: string
  programSearchConfigurationId: string
  sidebarId: string
  navbarId: string
  coursePreviewTemplateId: string
  pdfSettings: PdfSettings
}

export interface HomeLinkType {
  value: string
  label: string
}

export interface Footer {
  component: string
  content: Content[]
}

export interface Content {
  component: string
  content: string
}

export interface CoursesFilters {
  condition: string
  filters: Filter[]
}

export interface Filter {
  id: string
  name: string
  inputType: string
  group: string
  type: string
  value: any
  customField?: boolean
}

export interface DepartmentsFilters {
  condition: string
  filters: Filter[]
}

export interface InstructorsFilters {
  condition: string
  filters: Filter[]
}

export interface ProgramsFilters {
  condition: string
  filters: Filter[]
}

export interface PdfSettings {
  includeDepartments: boolean
  includePrograms: boolean
  includeCourses: boolean
  condensed: boolean
  applyWebsiteFont: boolean
  fontSize: number
  includeAllProgramsAndCourses: boolean
  includeCourseSetAndRequirementSetReferenceMaterials: boolean
}

export interface CourseSearchApiResponse {
  listLength: number
  data: CourseDogCourse[]
  limit: number
  skip: number
}

export interface CourseDogCourse {
  _id: string
  career: string
  code: string
  college: string
  courseGroupId: string
  courseNumber: string
  credits: Credits
  customFields: CustomFields
  departments: string[]
  description: string
  effectiveEndDate: any
  effectiveStartDate: string
  id: string
  longName: string
  name: string
  status: string
  subjectCode: string
  departmentOwnership: DepartmentOwnership[]
}

export interface Credits {
  creditHours: CreditHours
  billingHours: BillingHours
}

export interface CreditHours {
  min: number
  operator: string
}

export interface BillingHours {
  min?: number
  operator: string
}

export interface CustomFields {
  rawCourseId: string
}

export interface DepartmentOwnership {
  deptId: string
  percentOwnership: number
}

//#endregion