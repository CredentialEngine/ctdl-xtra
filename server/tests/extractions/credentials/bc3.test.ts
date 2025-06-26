import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Butler County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Technology",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/computer-technology/computer-programming-specialist.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Systems - Programming Specialist"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Become highly employable in the computer field after learning three programming languages: procedural, object-oriented and visual."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Physical Education - Teacher Education, A.S.",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/education/physical-education-teacher-education.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Physical Education - Teacher Education, A.S."),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Physical Education - Teacher Education, A.S. program is designed to prepare students for transfer to a four-year institution to complete a bachelor's degree and teacher certification in health and physical education."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Networking and Cybersecurity",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/computer-technology/networking-cybersecurity.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Networking and Cybersecurity"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Learn how computers share data, software and other resources via wireless (wi-fi) and client server networks and also the Internet."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Nursing, R.N. - Three-Year, A.A.S",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/health-care/nursing-three-year.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Nursing, R.N. - Three-Year, A.A.S"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Nursing, R.N. - Three-Year, A.A.S. program is designed to prepare students for transfer to a four-year institution to complete a bachelor's degree and teacher certification in health and physical education."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
 
  test(
    "Nanofabrication Technology",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/engineering-applied-technology/nanofabrication-technology.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Nanofabrication Technology"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "By utilizing biology, chemistry and engineering principles, learn to create extremely small electronic and mechanical devices."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 