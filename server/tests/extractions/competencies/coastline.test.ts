import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Coastline College", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Coastline College", () => {
    test("Accounting A101", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.cccd.edu/courses/acct-a101/"
      );

      expect(extractions).arrayContaining([
        {
          "competency_category": "outcomes",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Demonstrate knowledge of an accounting cycle by performing appropriate accounting functions.",
        },
        {
          "competency_category": "outcomes",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Demonstrate ability to prepare financial statements for a corporation.",
        },
        {
          "competency_category": "outcomes",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Prepare accounting entries required for a service versus merchandising business.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain the nature and purpose of generally accepted accounting principles (GAAP) and International Financial Reporting Standards (IFRS). Explain and apply the components of the conceptual framework for financial accounting and reporting, including the qualitative characteristics of accounting information, the assumptions underlying accounting, the basic principles of financial accounting, and the constraints and limitations on accounting information.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Define and use accounting and business terminology.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain what a system is and how an accounting system is designed to satisfy the needs of specific businesses and users; summarize the purpose of journals and ledgers.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Apply transaction analysis, input transactions into the accounting system, process this input, and prepare and interpret the four basic financial statements.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Distinguish between cash basis and accrual basis accounting and their impact on the financial statements, including the revenue recognition and matching principles.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Identify and illustrate how the principles of internal control are used to manage and control the firm?s resources and minimize risk.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain the content, form, and purpose of the basic financial statements (including footnotes) and the annual report, and how they satisfy the information needs of investors, creditors, and other users.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain the nature of current assets and related issues, including the measurement and reporting of cash and cash equivalents, receivables and bad debts, and inventory and cost of goods sold.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain the valuation and reporting of current liabilities, estimated liabilities, and other contingencies.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Identify and illustrate issues relating to long-term asset acquisition, use, cost allocation, and disposal.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Distinguish between capital and revenue expenditures.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Identify and illustrate issues relating to long-term liabilities, including issuance, valuation, and retirement of debt;(including the time value of money).",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Identify and illustrate issues relating to stockholders? equity, including issuance, repurchase of capital stock, and dividends.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Explain the importance of operating, investing and financing activities reported in the Statement of Cash Flows.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Interpret company activity, profitability, liquidity and solvency through selection and application of appropriate financial analysis tools.",
        },
        {
          "competency_category": "course_ives",
          "competency_framework": "Financial Accounting",
          "language": "en",
          "text": "Identify the ethical implications inherent in financial reporting and be able to apply strategies for addressing them.",
        },

      ]);
    });
  });
});
