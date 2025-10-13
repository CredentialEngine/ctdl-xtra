# Credentials are Diplomas or Badges obtained at the end of a learning program

The required fields are:
- Name
- Credential Type (enum) with:
  - [Certificate](https://credreg.net/ctdl/terms/Certificate#Certificate)
  - Certification
  - Degree
  - Diploma
  - License
  - Badge
  - Microcredential
  - ApprenticeshipCertificate
  - Assessment
  - LearningOpportunity
  - BootcampCertificate
  - DigitalBadge
  - JourneymanCertificate
  - MasterCertificate
  - ProfessionalCertificate
  - QualityAssuranceCredential
  - SecondarySchoolDiploma
  - TradeCertificate

```JSON
{
  "@context": "https://credreg.net/ctdl/schema/context/json",
  "@graph": [
    {
      "@type": "rdf:Property",
      "@id": "ceterms:credentialType",
      "rdfs:label": {
        "en-US": "Credential Type"
      },
      "rdfs:comment": {
        "en-US": "Type of credential such as badge, certification, bachelor degree."
      },
      "dct:description": {
        "en-US": "A general property for use where a resource needs to identify a specific sub-class of the ceterms:Credential type."
      },
      "vs:term_status": "vs:stable",
      "meta:changeHistory": "https://credreg.net/ctdl/termhistory/ceterms/credentialType/json",
      "schema:domainIncludes": [
        "ceterms:CredentialComponent"
      ],
      "schema:rangeIncludes": [
        "ceterms:AcademicCertificate",
        "ceterms:ApprenticeshipCertificate",
        "ceterms:AssociateDegree",
        "ceterms:BachelorDegree",
        "ceterms:Badge",
        "ceterms:BasicTechnicalCertificate",
        "ceterms:Certificate",
        "ceterms:CertificateOfCompletion",
        "ceterms:CertificateOfParticipation",
        "ceterms:Certification",
        "ceterms:Degree",
        "ceterms:DigitalBadge",
        "ceterms:Diploma",
        "ceterms:DoctoralDegree",
        "ceterms:GeneralEducationDevelopment",
        "ceterms:GeneralEducationLevel1Certificate",
        "ceterms:GeneralEducationLevel2Certificate",
        "ceterms:HigherEducationLevel1Certificate",
        "ceterms:HigherEducationLevel2Certificate",
        "ceterms:JourneymanCertificate",
        "ceterms:License",
        "ceterms:MasterCertificate",
        "ceterms:MasterDegree",
        "ceterms:MicroCredential",
        "ceterms:OpenBadge",
        "ceterms:PostBaccalaureateCertificate",
        "ceterms:PostMasterCertificate",
        "ceterms:PreApprenticeshipCertificate",
        "ceterms:ProfessionalCertificate",
        "ceterms:ProfessionalDoctorate",
        "ceterms:ProficiencyCertificate",
        "ceterms:QualityAssuranceCredential",
        "ceterms:ResearchDoctorate",
        "ceterms:SecondaryEducationCertificate",
        "ceterms:SecondarySchoolDiploma",
        "ceterms:TechnicalLevel1Certificate",
        "ceterms:TechnicalLevel2Certificate",
        "ceterms:TechnicalLevel3Certificate",
        "ceterms:WorkBasedLearningCertificate"
      ]
    }
  ]
}
```

University unit tests completed
bc3.test.ts - Butler County Community College
bismarc.test.ts - Bismarck State College
bucks.test.ts - Bucks
ccac.test.ts - Allegheny
ec3pa.test.ts - 
ivytech