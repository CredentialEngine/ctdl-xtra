// Faithful transliteration of ctdl-xtra's prompts + schemas from
// ctdl-xtra/common/catalogueTypes.ts + server/src/extraction/llm/extractEntityData.ts
// Goal: reproduce xTRA's baseline extraction behavior on Claude, unchanged.

const CREDENTIAL_TYPE_ENUM = [
  "AcademicCertificate", "ApprenticeshipCertificate", "AssociateDegree",
  "BachelorDegree", "Badge", "BasicTechnicalCertificate", "Certificate",
  "CertificateOfCompletion", "CertificateOfParticipation", "Certification",
  "Degree", "DigitalBadge", "Diploma", "DoctoralDegree",
  "GeneralEducationDevelopment", "GeneralEducationLevel1Certificate",
  "GeneralEducationLevel2Certificate", "HigherEducationLevel1Certificate",
  "HigherEducationLevel2Certificate", "JourneymanCertificate", "License",
  "MasterCertificate", "MasterDegree", "MicroCredential", "OpenBadge",
  "PostBaccalaureateCertificate", "PostMasterCertificate",
  "PreApprenticeshipCertificate", "ProfessionalCertificate",
  "ProfessionalDoctorate", "ProficiencyCertificate",
  "QualityAssuranceCredential", "ResearchDoctorate",
  "SecondaryEducationCertificate", "SecondarySchoolDiploma",
  "TechnicalLevel1Certificate", "TechnicalLevel2Certificate",
  "TechnicalLevel3Certificate", "WorkBasedLearningCertificate",
];

// --- CREDENTIALS baseline (verbatim from catalogueTypes.ts:431-546) ---

const CRED_PROPS = {
  credential_name: {
    description:
      'name for the credential or certificate (example: "Computer Science"). Don not include the type of credential in the name. Do not confuse the category of the credential with the specific name.',
    required: true,
  },
  credential_description: {
    description:
      "the description of the credential. Can be a short description or a long description, make sure to include all the details of the credential such as the opportunities it provides or descriptions of roles in the industry.",
    required: true,
  },
  credential_type: { description: "the type of credential.", required: true },
  language: {
    description:
      "The language in full (example: 'English', 'Spanish', 'German', etc.)",
    required: false,
  },
};

const CRED_DESIRED_OUTPUT = `
      We are looking for a list of credentials that are offered by the institution.
      Credentials are prof of completion of a course or learning program. They can be diplomas, certificates, badges, etc.
      If found, take each item exactly as it is in the page and return them. Skip everything else, just the credential list.
      Note that pages can show options to get other credentials, we only need the ones directly related to the course or learning program.
      Do not confuse credentials with courses or skills or learning outcomes. Do not list Certifications, those are not credentials. Return only the credentials that are offered by the institution.
      Ignore stackable certificates.
    `;

export const CRED_SCHEMA = {
  type: "object",
  properties: {
    items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          credential_name: { type: "string" },
          credential_description: { type: "string" },
          credential_type: { type: "string", enum: CREDENTIAL_TYPE_ENUM },
          language: { type: "string" },
        },
        required: [
          "credential_name",
          "credential_description",
          "credential_type",
          "language",
        ],
      },
    },
  },
  required: ["items"],
};

// --- LEARNING_PROGRAMS baseline (verbatim from catalogueTypes.ts:287-327) ---

const PROG_PROPS = {
  learning_program_id: {
    description:
      "code/identifier for the learning program. Unless it is clearly identified as such in the page, default to the name of the learning program.",
    required: true,
  },
  learning_program_name: {
    description:
      'name for the learning program (example: "Bachelor of Science in Computer Science")',
    required: true,
  },
  learning_program_description: {
    description: `the description of the learning program.
       Pages often include other sections aside from the basic description, for example containing program requirements,
       restrictions, etc. We don't want any of that - we only want the program description (directly extracted from the page).
       You should take only the first few paragraphs of the description.
       If there are links, only extract the text.
      `,
    required: true,
  },
};

export const PROG_SCHEMA = {
  type: "object",
  properties: {
    items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          learning_program_id: { type: "string" },
          learning_program_name: { type: "string" },
          learning_program_description: { type: "string" },
        },
        required: [
          "learning_program_id",
          "learning_program_name",
          "learning_program_description",
        ],
      },
    },
  },
  required: ["items"],
};

// --- Prompt assembly (mirrors extractEntityData.ts:getBasePrompt + main body) ---

function buildFieldList(props) {
  return Object.entries(props)
    .map(([k, p]) => `${k}: ${p.description}${p.required ? " (REQUIRED)" : ""}`)
    .join("\n");
}

export function buildXtraPrompt({ entityName, desiredOutput, props, url, content }) {
  return `
Your goal is to extract ${entityName} data from this page.
       Extract the data EXACTLY as it shows up in the page.
       NEVER paraphrase, rewrite or change content unless requested.

${desiredOutput || ""}
We are looking for the following fields:
${buildFieldList(props)}

PAGE URL:

${url}

SIMPLIFIED PAGE CONTENT:

\`\`\`markdown
${content}
\`\`\`

`;
}

export const XTRA_CONFIGS = {
  credential: {
    entityName: "credential",
    desiredOutput: CRED_DESIRED_OUTPUT,
    props: CRED_PROPS,
    schema: CRED_SCHEMA,
  },
  learning_program: {
    entityName: "learning program",
    desiredOutput: "",
    props: PROG_PROPS,
    schema: PROG_SCHEMA,
  },
};
