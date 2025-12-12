import { Link } from "wouter";
import { CatalogueType } from "../../../../common/types";
import { catalogueTypes } from "../../../../common/catalogueTypes";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";

export default function Welcome() {
  return (
    <div className="space-y-8">
      {/* Main Title */}
      <div>
        <h1 className="text-2xl font-semibold md:text-3xl">
          Welcome to Credential Engine's AI Crawler
        </h1>
      </div>

      {/* Description Box */}
      <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 md:p-6">
        <p className="text-sm md:text-base text-gray-700">
          This tool is designed to crawl public web pages, extract content, and transform it into Credential Transparency Description Language (CTDL) formats for easy upload to the Credential Registry Publishing System using pre-defined bulk upload templates.
        </p>
      </div>

      {/* Current Capabilities Section */}
      <div>
        <h2 className="text-xl font-semibold mb-4">Current Capabilities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            CatalogueType.COURSES,
            CatalogueType.CREDENTIALS,
            CatalogueType.LEARNING_PROGRAMS,
            CatalogueType.COMPETENCIES,
          ].map((type) => {
            const definition = catalogueTypes[type];
            return (
              <Card key={type} className="flex flex-col">
                <CardHeader className="pb-3">
                  <div className="flex flex-col gap-2">
                    <CardTitle className="text-lg">{definition.displayTitle}</CardTitle>
                    <Badge
                      variant={definition.isActive ? "default" : "secondary"}
                      className={
                        definition.isActive
                          ? "bg-green-500 text-white border-green-600 w-fit"
                          : "bg-gray-200 text-gray-700 border-gray-300 w-fit"
                      }
                    >
                      {definition.isActive ? "Active" : "Coming Soon"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-sm">
                    {definition.displayDescription}
                  </CardDescription>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Two Column Layout: How It Works and Getting Started/Contact */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* How It Works - Left Side (2 columns) */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">How It Works</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4 list-decimal list-inside">
                <li className="text-sm md:text-base">
                  <span className="font-medium">Account Setup:</span>{" "}
                  Users must have an account set up by the Credential Engine team to access the tool.
                </li>
                <li className="text-sm md:text-base">
                  <span className="font-medium">Provide the URL:</span>{" "}
                  Enter the URL that directly displays the course content. For course catalogs, use the URL that shows a list of course descriptions or links. The AI Crawler requires the courses to be visible directly on the page.
                </li>
                <li className="text-sm md:text-base">
                  <span className="font-medium">Crawling Process:</span>{" "}
                  Once you enter the URL, the tool will begin crawling the web pages. You don't need to keep the browser window open—just wait for two emails from the system. The first email will notify you that the crawling process has started. The second email will inform you whether the data extraction and transformation were successful or failed.
                </li>
                <li className="text-sm md:text-base">
                  <span className="font-medium">Download the Results:</span>{" "}
                  If the process is successful, the email will include a link to download the pre-defined bulk upload template. The template is ready for use, with the header row formatted for bulk upload. Each subsequent row represents a single resource, such as a course.
                </li>
                <li className="text-sm md:text-base">
                  <span className="font-medium">Review and Upload:</span>{" "}
                  After downloading the bulk upload CSV, review it for accuracy. Once confirmed, you can upload it to the Credential Registry Publishing System using the Bulk Upload System.
                </li>
              </ol>
            </CardContent>
          </Card>
        </div>

        {/* Getting Started and Contact - Right Side (1 column) */}
        <div className="space-y-4">
          {/* Getting Started Box */}
          <Card className="bg-orange-50 border-orange-200">
            <CardHeader>
              <CardTitle className="text-lg">Getting Started</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-700">
                To begin a new extraction, select{" "}
                <Link to="/catalogues" className="text-blue-600 hover:underline">
                  "Catalogues"
                </Link>{" "}
                from the menu, then choose{" "}
                <Link to="/catalogues/new" className="text-blue-600 hover:underline">
                  "+Add Catalogue"
                </Link>
                .
              </p>
            </CardContent>
          </Card>

          {/* Contact Credential Engine Box */}
          <Card className="bg-blue-50 border-blue-200">
            <CardHeader>
              <CardTitle className="text-lg">Contact Credential Engine</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-700">
                Email{" "}
                <a
                  href="mailto:publishing@credentialengine.org"
                  className="text-blue-600 hover:underline"
                >
                  publishing@credentialengine.org
                </a>{" "}
                for assistance. We check this email regularly during normal U.S. business hours.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
