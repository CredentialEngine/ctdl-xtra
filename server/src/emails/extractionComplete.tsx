import { CompletionStats } from "@common/types";
import {
  Body,
  Button,
  Column,
  Container,
  Head,
  Hr,
  Html,
  Link,
  Preview,
  Row,
  Section,
  Text,
} from "@react-email/components";
import { buildFrontendUrl } from "../utils";
import * as styles from "./styles";

export interface ExtractionCompleteProps {
  extractionId: number;
  recipeId: number;
  catalogueId: number;
  catalogueName: string;
  url: string;
  completionStats: CompletionStats;
  createdAt: string;
  stale?: boolean;
}

function toIsoDate(dateString: string) {
  // Check if the dateString already contains 'T' and ends with 'Z'
  if (!dateString.includes("T") || !dateString.endsWith("Z")) {
    // Replace the space between date and time with a 'T'
    dateString = dateString.replace(" ", "T");
    // Add the 'Z' at the end to indicate UTC time
    dateString += "Z";
  }

  return new Date(dateString);
}

function formatDuration(ms: number): string {
  const hours = ms / 1000 / 60 / 60;
  const minutes = ms / 1000 / 60;

  if (hours >= 1) {
    return `${hours.toFixed(1)} hours`;
  } else {
    return `${minutes.toFixed(1)} minutes`;
  }
}

function ExtractionStats(props: { completionStats: CompletionStats }) {
  return (
    <Section>
      <Row>
        <Column>Pages Crawled</Column>
      </Row>
    </Section>
  );
}

const ExtractionComplete = ({
  extractionId,
  recipeId,
  catalogueId,
  catalogueName,
  url,
  completionStats,
  createdAt,
  stale,
}: ExtractionCompleteProps) => {
  const extractionUrl = buildFrontendUrl(`/extractions/${extractionId}`);
  const datasetUrl = buildFrontendUrl(`/datasets/courses/${extractionId}`);
  const elapsedTimeMs =
    new Date(completionStats.generatedAt).getTime() -
    toIsoDate(createdAt).getTime();
  const elapsedTime = formatDuration(elapsedTimeMs);
  let totalCourses = 0,
    totalPageDownloads = 0,
    totalPageErrors = 0;
  for (const step of completionStats.steps) {
    totalCourses += step.extractions.courses;
    totalPageDownloads += step.downloads.succeeded;
    totalPageErrors += step.downloads.total - step.downloads.succeeded;
  }

  return (
    <Html lang="en">
      <Head />
      <Preview>An extraction has finished</Preview>
      <Body style={styles.main}>
        <Container style={styles.container}>
          <Text style={styles.title}>
            Hi! An <Link href={extractionUrl}>extraction</Link> has finished for
            the {catalogueName} catalogue.
          </Text>
          {stale ? (
            <Text style={styles.warning}>
              Unfortunately, the extraction was marked as finished because it
              was stale. That indicates a problem might have happened during the
              extraction.
            </Text>
          ) : null}
          <Section style={styles.dataSection}>
            <Row>
              <Column style={styles.dataColumnHeader}>Root URL</Column>
              <Column>
                <Link href={url}>{url}</Link>
              </Column>
            </Row>
            <Row>
              <Column style={styles.dataColumnHeader}>Duration</Column>
              <Column>{elapsedTime}</Column>
            </Row>
            <Hr />
            <Row>
              <Column style={styles.dataColumnHeader}>Page Downloads</Column>
              <Column>{totalPageDownloads}</Column>
            </Row>
            <Row>
              <Column style={styles.dataColumnHeader}>Page Errors</Column>
              <Column>{totalPageErrors}</Column>
            </Row>
            <Row>
              <Column style={styles.dataColumnHeader}>Courses Extracted</Column>
              <Column>{totalCourses}</Column>
            </Row>
          </Section>
          <Text>To check out the extracted data, click the button below.</Text>
          <Button style={styles.button} href={datasetUrl}>
            View {totalCourses} courses
          </Button>
          <Text style={styles.footer}>Credential Engine - CTDL xTRA</Text>
        </Container>
      </Body>
    </Html>
  );
};

ExtractionComplete.DefaultSubject = "Extraction has finished";
ExtractionComplete.PreviewProps = {
  extractionId: 1,
  recipeId: 1,
  catalogueId: 1,
  catalogueName: "Test Catalogue",
  url: "https://www.learningtapestry.com",
  completionStats: {
    steps: [
      {
        downloads: {
          total: 10,
          attempted: 10,
          succeeded: 10,
        },
        extractions: {
          attempted: 10,
          succeeded: 10,
          courses: 10,
        },
      },
      {
        downloads: {
          total: 10,
          attempted: 10,
          succeeded: 10,
        },
        extractions: {
          attempted: 10,
          succeeded: 10,
          courses: 10,
        },
      },
    ],
    generatedAt: "2024-07-17T19:06:59.000Z",
  },
  createdAt: "2024-07-17 19:05:57",
  stale: true,
} as ExtractionCompleteProps;

export default ExtractionComplete;
