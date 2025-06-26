import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Bucks County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Science",
    async () => {
      const url = "https://www.bucks.edu/academics/courses/majors/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Science"),
          credential_description: expect.like(
            "Associate degree program providing foundation in computer programming, algorithms, data structures, and software development"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Business Administration",
    async () => {
      const url = "https://www.bucks.edu/catalog/majors/business/business-administration/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Administration"),
          credential_description: expect.any(String),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "This program of study prepares students for upper-division course work leading to a bachelor's degree in Business Administration. The program parallels the first two years of study required by similar programs offered at baccalaureate institutions and universities. Students select the area of concentration best suited to their interests and aptitudes. This program is accredited by the Accreditation Council for Business Schools and Programs (ACBSP)."
          // ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Fine Arts",
    async () => {
      const url = "https://www.bucks.edu/catalog/majors/arts/arts/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Fine Arts"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The major equips the art student with the skills, techniques, and knowledge necessary for further training in a four-year professional or liberal arts institution and develops a strong base in arts, crafts, and design in the student whose formal education ends after two years at the College. For all Fine Arts majors, regardless of track, a portfolio review is recommended for placement purposes. An art advisor will help select the appropriate sequence of courses. Graduates of this program are able to apply technical skills associated with visual arts and design; develop a personal approach to creative problem-solving; and present a formal, professional-quality portfolio of work. The program includes an array of digital skills necessary for portfolio preparation and presentation. Bucks County Community College is an accredited institutional member of the National Association of Schools of Art and Design."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Emergency Management",
    async () => {
      const url = "https://www.bucks.edu/catalog/majors/business/emergencymanagementcertificate/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Emergency Management"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "This certificate program provides students an opportunity to pursue a career in emergency management or for professional development for those currently employed or who already have a degree in another field. The Emergency Management Certificate Program, which is aligned with the Emergency Management Institute’s Higher Education Program and the Principles of Emergency Management, prepares the student for a position in Emergency Management, Business Continuity, and related disciplines."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Magnetic Resonance Imaging",
    async () => {
      const url = "https://www.bucks.edu/catalog/majors/health/magneticresonanceimaging/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Magnetic Resonance Imaging"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The MRI Certificate program is a two-semester program. The program consists of online didactic courses and a clinical practicum experience. The MRI Certificate Program is designed to provide the working Radiologic Technologist with the theoretical background and documented clinical experience necessary to sit for the Magnetic Resonance Imaging Post-Primary Certification exam offered by the American Registry of Radiologic Technologist (ARRT)."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Journalism",
    async () => {
      const url = "https://www.bucks.edu/catalog/majors/language/journalism/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Journalism"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Journalism major prepares students for news reporting, writing, copy editing, and page layout in both print and online journalism. The courses parallel the offerings in the first two years of most four-year journalism programs. The weekly campus newspaper provides practical workshop experience. Students gain computer skills by writing stories in computer labs and by using the Internet and electronic databases to gather information."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 