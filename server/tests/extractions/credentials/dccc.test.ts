import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Delaware County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Art + Design Studies",
    async () => {
      const url = "https://catalog.dccc.edu/academic-programs/art-design/";
      const credentials = await extractCredentials(url);

      expect(credentials).arrayContaining([
        {
          credential_name: expect.like("Art - Studio (STU)"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Associate in Fine Arts (AFA) in Art - Studio concentrates on painting and drawing. Experienced and accomplished faculty members mentor students as they cultivate skills and build a portfolio required for transfer into a four-year Bachelor of Fine Arts (BFA) program."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
        {
          credential_name: expect.like("Graphic Design (GRA)"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Associate of Fine Art degree program in graphic design teaches students how to develop design concepts and aesthetically arrange type and image in order to plan and produce intelligent visual communication solutions to client problems or self-authored work."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
        {
          credential_name: expect.like("Photography (PHO)"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Photography program develops professional image-makers through student-centered inquiry and practice in visual communication."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
        {
          credential_description: expect.like(
            "The Art + Design Foundations Certificate (ADFC) is a 30-credit, studio-based curriculum, which includes 2D design, 3D design, drawing, color theory, art history, digital art, art electives, and general education. The Art + Design Foundations Certificate covers the first year of an art program during which students learn the fundamentals of art and design, methods and materials, art history, and the process of creative thinking. The foundation year is essential to providing students with a base of skills and knowledge necessary for upper level coursework in the visual arts."
          ),
          credential_name: expect.like("Art + Design Foundations"),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 