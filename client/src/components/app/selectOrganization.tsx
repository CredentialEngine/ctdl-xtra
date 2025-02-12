
import { UserContext } from "@/userContext";
import { useContext, useEffect, useState } from "react";
import { Button } from "../ui/button";
import { useLocation } from "wouter";
import { AlertCircle, ChevronRight, LucideBriefcaseBusiness } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { Alert, AlertTitle, AlertDescription } from '../ui/alert';

function autoSelectOrgIfSingleMembership(query, onSelect, onError): void {
  if (query?.data?.length > 1 || !query.isFetched) {
    return;
  }

  const [firstMembership] = query?.data;
  if (!firstMembership) {
    onError(new Error("No organizations assigned to the user. Please try signing out or contact the system administrator."))
    return;
  }

  onSelect(firstMembership.orgs.id);
}


export const SelectOrganization = () => {
  const { orgId, setOrgId, userOrgsQuery } = useContext(UserContext);
  const [_, setLocation] = useLocation();
  const [error, setError] = useState<Error | undefined>();

  useEffect(
    autoSelectOrgIfSingleMembership.bind(null, userOrgsQuery, setOrgId, setError),
    [userOrgsQuery?.state]
  )

  if (userOrgsQuery?.isLoadingError) {
    return (<div>{userOrgsQuery?.error?.message}</div>)
  }

  if (userOrgsQuery?.isLoading) {
    return (<div>Loading...</div>);
  }

  return (
    <div className="w-full h-dvh flex flex-col items-center justify-center">
      <h1 className="m-4">Select organization</h1>
      {error &&
        (
          <Card>
            <CardContent>
              { }
            </CardContent>
          </Card>
        )
      }
      {userOrgsQuery?.data?.map(item =>
      (
        <Button className="w-80 m-2 flex flex-row flex-no-wrap justify-between" variant="outline" onClick={() => setLocation(`/org/{item.orgs?.id}`)}>
          <LucideBriefcaseBusiness />
          <span>{item.orgs.name}</span>
          <ChevronRight />
        </Button>
      )
      )}
    </div>
  );
}

export function Error({ error }: { error: object }) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Error</AlertTitle>
      <AlertDescription>
        {error?.message}
      </AlertDescription>
    </Alert>
  )
}