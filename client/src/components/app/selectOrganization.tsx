import { UserContext, UserContextProps } from "@/userContext";
import { useContext, useEffect, useState } from "react";
import { Link } from "wouter";
import { AlertCircle, LoaderIcon } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { Alert, AlertTitle, AlertDescription } from "../ui/alert";
import { OrgSelector } from "../ui/org-selector";

export const SelectOrganization = () => {
  const { setCurrentOrganizationId, userOrgsQuery } = useContext(UserContext);
  const [error, setError] = useState<Error | undefined>();

  useEffect(
    () => autoSelectOrgIfSingleMembership(userOrgsQuery, setCurrentOrganizationId, setError),
    [userOrgsQuery?.status]
  );

  const orgSelectorItems = userOrgsQuery?.data?.map((item) => ({
    key: item.orgs.id,
    linkProps: { to: `/org/${item.orgs?.id}` },
    text: item.orgs.name,
  }));

  const Items = (
    <OrgSelector
      items={orgSelectorItems || []}
      LinkComponent={Link}
      density="relaxed"
    />
  );

  return (
    <div className="w-full h-dvh flex flex-col items-center justify-center">
      <h1 className="m-4">Select organization</h1>
      {error && (
        <Card>
          <CardContent>{}</CardContent>
        </Card>
      )}
      {userOrgsQuery?.isLoading ? (
        <LoaderIcon className="animate-spin mr-2 w-3.5" />
      ) : (
        Items
      )}
    </div>
  );
};

export function ErrorAlert({ error }: { error: Error }) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Error</AlertTitle>
      <AlertDescription>{error?.message}</AlertDescription>
    </Alert>
  );
}

function autoSelectOrgIfSingleMembership(
  query: UserContextProps["userOrgsQuery"],
  onSelect: (id?: UserContextProps["currentOrganizationId"]) => void,
  onError: (e: Error) => void
) {
  if (query?.data?.length! > 1 || !query?.isFetched) {
    return;
  }

  const [firstMembership] = query?.data || [];
  if (!firstMembership) {
    onError(
      new Error(
        "No organization assigned to the accoount. Please try signing in/out."
      )
    );
    return;
  }

  onSelect(firstMembership.orgs.id);
}
