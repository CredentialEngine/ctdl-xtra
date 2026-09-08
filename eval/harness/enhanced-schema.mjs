// Enhanced CTDL extraction schema — what xTRA COULD extract with a wider net.
// Field set drawn from CTDL Minimum Data Policy + recommended properties for
// Credential + LearningOpportunityProfile (see ../ctdl-reference/field-spec.md).
//
// Note: this enum is a curated CTDL-correct subset (includes degree sub-types
// like BachelorOfScienceDegree). It intentionally differs from xTRA's 38-value
// enum in xtra-prompts.mjs, which is preserved verbatim for the baseline.

const strArr = (description, enum_) => ({
  type: ["array", "null"],
  items: enum_ ? { type: "string", enum: enum_ } : { type: "string" },
  description,
});

const CREDENTIAL_TYPE_ENUM = [
  "AcademicCertificate", "ApprenticeshipCertificate", "AssociateDegree",
  "AssociateOfAppliedArtsDegree", "AssociateOfAppliedScienceDegree",
  "AssociateOfArtsDegree", "AssociateOfScienceDegree", "BachelorDegree",
  "BachelorOfArtsDegree", "BachelorOfScienceDegree", "Badge", "Certificate",
  "CertificateOfCompletion", "Certification", "Degree", "DigitalBadge",
  "Diploma", "DoctoralDegree", "License", "MasterDegree",
  "MasterOfArtsDegree", "MasterOfScienceDegree", "MicroCredential",
  "OpenBadge", "PostBaccalaureateCertificate", "ProfessionalCertificate",
  "ProfessionalDoctorate", "ResearchDoctorate", "SecondarySchoolDiploma",
];

const DELIVERY_TYPE_ENUM = [
  "BlendedDelivery", "InPerson", "OnlineOnly", "MultipleDelivery",
];

const AUDIENCE_LEVEL_ENUM = [
  "AdvancedLevel", "AssociatesDegreeLevel", "BachelorsDegreeLevel",
  "BeginnerLevel", "DoctoralDegreeLevel", "GraduateLevel",
  "IntermediateLevel", "LowerDivisionLevel", "MastersDegreeLevel",
  "PostSecondaryLevel", "ProfessionalLevel", "SecondaryLevel",
  "UndergraduateLevel", "UpperDivisionLevel",
];

const STATUS_ENUM = ["Active", "Deprecated", "Probationary", "Suspended", "TeachOut"];

export const ENHANCED_SCHEMA = {
  type: "object",
  properties: {
    // --- identity ---
    name: {
      type: "string",
      description:
        "Full official name of the credential/program as the institution publishes it, including degree type. Ex: 'Bachelor of Science in Computer Science', 'Master of Business Administration'.",
    },
    alternateName: {
      type: ["string", "null"],
      description: "Abbreviation or alternate name if given (ex: 'BSCS', 'MBA').",
    },
    description: {
      type: "string",
      description:
        "The program's overview/description prose. First 2-4 paragraphs of the main description, verbatim. Do not include requirements, courses, or outcome lists here.",
    },
    credentialType: {
      type: "string",
      enum: CREDENTIAL_TYPE_ENUM,
      description: "CTDL credential subclass.",
    },
    subjectWebpage: {
      type: "string",
      description: "The canonical URL of this program's page (usually the input URL).",
    },
    inLanguage: {
      type: "string",
      description: "BCP-47 language code of instruction (ex: 'en', 'en-US').",
    },
    credentialStatusType: {
      type: "string",
      enum: STATUS_ENUM,
      description:
        "Lifecycle status. If page says nothing about deprecation/teach-out, use 'Active'.",
    },
    // --- delivery & audience ---
    learningDeliveryType: strArr(
      "How it's delivered. Infer from '100% online', 'on campus', etc.",
      DELIVERY_TYPE_ENUM
    ),
    audienceLevelType: strArr(
      "Academic level of the intended audience.",
      AUDIENCE_LEVEL_ENUM
    ),
    // --- time & credits ---
    estimatedDuration: {
      type: ["object", "null"],
      properties: {
        exactDuration: {
          type: ["string", "null"],
          description: "ISO 8601 duration if a single figure is given (ex: 'P24M', 'P4Y').",
        },
        minimumDuration: {
          type: ["string", "null"],
          description: "ISO 8601, if a range or 'as fast as' is given.",
        },
        maximumDuration: { type: ["string", "null"] },
        description: {
          type: ["string", "null"],
          description: "Source text about time-to-complete, verbatim.",
        },
      },
      description:
        "Time to complete. Convert on-page phrases like 'most students finish in 24 months' to ISO 8601.",
    },
    creditValue: {
      type: ["object", "null"],
      properties: {
        value: { type: ["number", "null"] },
        creditUnitType: {
          type: ["string", "null"],
          enum: [
            "DegreeCredit", "SemesterHour", "QuarterHour", "CompetencyCredit",
            "ContactHour", "ClockHour", "CarnegieUnit", "ContinuingEducationUnit",
            null,
          ],
        },
        description: { type: ["string", "null"] },
      },
      description: "Total credits/competency-units required to complete.",
    },
    // --- cost ---
    estimatedCost: {
      type: ["array", "null"],
      items: {
        type: "object",
        properties: {
          costType: {
            type: "string",
            enum: [
              "Tuition", "AggregateCost", "ApplicationFee", "EnrollmentFee",
              "BooksAndSupplies", "TechnologyFee", "ProgramFee",
            ],
          },
          price: { type: ["number", "null"] },
          currency: { type: "string", description: "ISO 4217, ex 'USD'." },
          paymentPattern: {
            type: ["string", "null"],
            description: "'per term', 'per credit', 'total', etc.",
          },
          description: { type: ["string", "null"] },
        },
        required: ["costType", "currency"],
      },
      description: "All cost figures found on the page.",
    },
    // --- requirements ---
    requires: {
      type: ["object", "null"],
      properties: {
        description: {
          type: ["string", "null"],
          description:
            "Free-text summary of admission requirements as on the page.",
        },
        prerequisiteCredentials: {
          type: ["array", "null"],
          items: { type: "string" },
          description:
            "Named prerequisite credentials (ex: 'high school diploma', 'RN license', 'bachelor's degree').",
        },
        yearsOfExperience: { type: ["number", "null"] },
        minimumAge: { type: ["number", "null"] },
      },
      description: "Admission / entry requirements (CTDL ConditionProfile).",
    },
    // --- outcomes ---
    teaches: strArr(
      "Learning outcomes / competencies / skills the program teaches, one per item, verbatim from the page."
    ),
    occupationType: strArr(
      "Career/job titles this prepares you for (ex: 'Software Developer', 'Registered Nurse'). Free text; O*NET/SOC coding is a downstream step."
    ),
    industryType: strArr(
      "Industries mentioned (ex: 'Healthcare', 'Information Technology')."
    ),
    // --- structure ---
    hasPart: {
      type: ["array", "null"],
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          codedNotation: { type: ["string", "null"] },
        },
        required: ["name"],
      },
      description:
        "Courses that make up the program, if listed on the page. Name + course code.",
    },
    // --- QA / relationships ---
    accreditedBy: strArr("Names of accrediting bodies mentioned."),
    industryCertifications: strArr(
      "Third-party certifications the program includes or prepares for (ex: 'CompTIA A+', 'AWS Cloud Practitioner')."
    ),
    keyword: strArr("Subject keywords/tags if the page lists them."),
    // --- provenance ---
    _extractionNotes: {
      type: ["string", "null"],
      description:
        "Anything relevant on the page that didn't fit a field above, or ambiguities you noticed.",
    },
  },
  required: [
    "name", "description", "credentialType", "subjectWebpage",
    "inLanguage", "credentialStatusType",
  ],
};

export const ENHANCED_SYSTEM = `You are extracting structured credential metadata for the Credential Registry using CTDL (Credential Transparency Description Language).

CTDL is a linked-data vocabulary. You will receive a program page from an educational institution and must populate a CTDL-aligned record.

Rules:
- Populate every field for which the page provides evidence. Use null for fields with no on-page evidence.
- Quote or lightly normalize source text; never invent facts not on the page.
- For enum fields, pick the closest CTDL term; do not free-text.
- Durations: convert to ISO 8601 (P4Y = 4 years, P24M = 24 months, PT120H = 120 hours).
- Costs: extract every price you see with its unit ("per 6-month term", "total", etc.).
- If a field's evidence is on a linked sibling page (tuition tab, admissions page) that you were NOT given, leave it null and note it in _extractionNotes.`;

export function buildEnhancedPrompt({ url, content }) {
  return `Extract a CTDL record for the credential/program described on this page.

PAGE URL: ${url}

PAGE CONTENT (simplified markdown):

\`\`\`markdown
${content}
\`\`\``;
}
