export class CourseDogAPIService {
  apiBase = "https://app.coursedog.com/api/v1";

  public async getCatalogs(schoolId: string): Promise<CourseDogCatalog[]> {
    return fetch(`${this.apiBase}/ca/${schoolId}/catalogs`)
      .then(r => r.json() as Promise<CourseDogCatalog[]>)
  }

  public async getCourses(schoolId: string, catalogId: string) {
    // Temporary early PoC implementation, requires better error handling
    // and simpler logic.

    const results: CourseDogCourse[] = [];
    const urlTemplate = `${this.apiBase}/ca/${schoolId}/courses/search/%24filters` +
      `?catalogId=${catalogId}` +
      `&skip={skip}` +
      `&limit=20` +
      `&orderBy=catalogDisplayName%2CtranscriptDescription%2ClongName%2Cname` +
      `&formatDependents=false` +
      `&effectiveDatesRange=2024-09-03%2C2025-08-20` +
      `&columns=customFields.rawCourseId%2CcustomFields.crseOfferNbr%2CcustomFields.catalogAttributes` +
      `%2CdisplayName%2Cdepartment%2Cdescription%2Cname%2CcourseNumber%2CsubjectCode%2Ccode%2CcourseGroupId` +
      `%2Ccareer%2Ccollege%2ClongName%2Cstatus%2Cinstitution%2CinstitutionId%2Ccredits`;
    const limit = 20;

    let numCalls = 1;
    let listLength = 0;

    for (let i = 0; i < numCalls; i++) {
      const skipValue = i * limit;
      const pageUrl = urlTemplate.replace("{skip}", String(skipValue));
      const data = await fetch(pageUrl).then(r => r.json() as Promise<CourseSearchApiResponse>);

      listLength = data.listLength;
      numCalls = Math.ceil(listLength / limit);
      
      results.push(...data);
    }
  }
}

//#region Types
export interface CourseDogCatalog {
  _id: string
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