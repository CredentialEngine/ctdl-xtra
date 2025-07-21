import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Bismarck State College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Advanced Digital Technologies",
    async () => {
      const url =
        "https://catalog.bismarckstate.edu/catalog/degrees/career-technical-education/advanced-digital-technologies/";
      const credentials = await extractCredentials(url);

      // Verify the credential details
      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Advanced Digital Technologies"),
          credential_description: expect.stringContaining("digital technology"),
          // Refer to [volatile] in the codebase.
          // credential_description: expect.like(
          //   "With an ever-changing workplace, many employers desire graduates who have well-rounded educational backgrounds including skills related to digital technology. The Advanced Digital Technology degree offers students an opportunity to combine three short-term certificates (16+ credits each) that are job skill related into one AAS degree. The certificates would include coursework from technical fields including cybersecurity, mobile application development, management, and exercise science. The Advanced Digital Technologies degree empowers students to customize their degree based on educational and professional goals. The short-term certificates are designed to provide you with workforce-ready technical skills in addition to strengthening your critical thinking, analysis, problem solving, and communication skills."
          // ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Networking",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/Computer%20Networking";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Computer Networking"),
          // Refer to [volatile] in the codebase.
          // credential_description: expect.like(
          //   `The Certificate in Computer Networking is a great way to kick-start your career. You may choose from online and on-campus course-delivery options. This flexibility allows you to complete coursework at your convenience and on your schedule.`
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Cybersecurity and Computer Networks",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/computersupport";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Cybersecurity and Computer Networks"),
          // Refer to [volatile] in the codebase.
          // credential_description: expect.like(
          //   `This degree program combines system administration fundamentals with a foundation in cybersecurity concepts. Classes focus on best practices to implement, administer, and secure operating systems and computer networks.`
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Cybersecurity and Information Technology (BAS)",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/BASinCybersecurityandInformationTechnology";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Cybersecurity and Information Technology"),
          // Refer to [volatile] in the codebase.
          // credential_description: expect.like(
          //   `This degree program provides a solid cybersecurity backing to information technology (IT) tasks. Classes focus on best practices to implement, administer, and secure the technologies used to process, transmit, and store data. Graduates gain hands-on experience securing network communications, configuring virtualization, managing cloud-based resources, and performing other common security-related tasks while administering daily IT operations.

          // These practical IT experiences are constructed using continual feedback from local, regional, and global cybersecurity practitioners. This assessment ensures students learn modern IT practices and receive the latest in cybersecurity education. Upon graduation, students are ready to use their knowledge and skills in the workforce of today and tomorrow.`
          // ),
          credential_description: expect.any(String),
          credential_type: "BachelorDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Offensive and Defensive Security",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/Offensive%20and%20Defensive%20Security";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Offensive and Defensive Security"),
          credential_description: expect.stringContaining("digital forensics"),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Security and Hacking",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/Security%20and%20Hacking";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Security and Hacking"),
          // Refer to [volatile] in the codebase.
          // credential_description: expect.like(
          //   "The Certificate in Security and Hacking is a great way to jump-start your career. You may choose from online and on-campus course-delivery options. This flexibility allows you to complete coursework at your convenience and on your schedule."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
});
