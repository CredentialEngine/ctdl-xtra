import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { trpc } from "@/utils";
import { Link, useLocation, useParams } from "wouter";

export default function DeleteUser() {
  const { userId } = useParams();
  const userQuery = trpc.users.detail.useQuery(
    { id: parseInt(userId || "") },
    { enabled: !!parseInt(userId || "") }
  );
  const deleteUser = trpc.users.delete.useMutation();
  const [_location, navigate] = useLocation();
  const { toast } = useToast();

  if (!userQuery.data) {
    return null;
  }

  async function onConfirmDeletion() {
    await deleteUser.mutateAsync({
      id: parseInt(userId as string),
    });
    toast({
      title: "User deleted",
      description: "The user was deleted successfully.",
    });
    navigate("~/users");
  }

  const breadCrumbs = [{ label: "Users", href: "/" }];

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Delete user</h1>
      </div>
      <div className="">
        Please confirm you'd like to delete the user{" "}
        <i>{userQuery.data.email}</i>.
      </div>
      <div>
        <Button onClick={onConfirmDeletion} variant={"destructive"}>
          Confirm user deletion
        </Button>
        <Button asChild variant={"outline"} className="ml-2">
          <Link to={"/"}>Cancel</Link>
        </Button>
      </div>
    </>
  );
}
