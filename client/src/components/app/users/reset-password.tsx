import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { copyToClipboard, trpc } from "@/utils";
import { Link, useLocation, useParams } from "wouter";

import { Copy } from "lucide-react";
import { useState } from "react";

export default function ResetUserPassword() {
  const [generatedPasswordOpen, setGeneratedPasswordOpen] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState<
    string | undefined
  >(undefined);
  const { userId } = useParams();
  const userQuery = trpc.users.detail.useQuery(
    { id: parseInt(userId || "") },
    { enabled: !!parseInt(userId || "") }
  );
  const resetPassword = trpc.users.resetPassword.useMutation();
  const [_location, navigate] = useLocation();

  if (!userQuery.data) {
    return null;
  }

  async function onConfirmPasswordReset() {
    const result = await resetPassword.mutateAsync({
      id: parseInt(userId as string),
    });
    setGeneratedPassword(result.generatedPassword);
    setGeneratedPasswordOpen(true);
  }

  function onClosePassword(open: boolean) {
    if (!open) {
      setGeneratedPassword(undefined);
      setGeneratedPasswordOpen(false);
      navigate("~/users");
    }
  }

  const breadCrumbs = [{ label: "Users", href: "/" }];

  async function copyPassword() {
    await copyToClipboard(generatedPassword!);
  }

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">
          Reset user password
        </h1>
      </div>
      <div className="">
        Please confirm you'd like to reset the password for{" "}
        <i>{userQuery.data.email}</i>.
      </div>
      <div>
        <Button onClick={onConfirmPasswordReset} variant={"destructive"}>
          Confirm password reset
        </Button>
        <Button asChild variant={"outline"} className="ml-2">
          <Link to={"/"}>Cancel</Link>
        </Button>
      </div>

      <Dialog open={generatedPasswordOpen} onOpenChange={onClosePassword}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Generated password</DialogTitle>
            <DialogDescription>
              The password was reset successfully. <br />
              The following password has been generated. It will only be shown
              once:
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center space-x-2">
            <div className="grid flex-1 gap-2">
              <Label htmlFor="password" className="sr-only">
                Password
              </Label>
              <Input id="password" value={generatedPassword} readOnly />
            </div>
            <Button
              type="submit"
              size="sm"
              className="px-3"
              onClick={copyPassword}
            >
              <span className="sr-only">Copy</span>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          <DialogFooter className="sm:justify-start">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Close
              </Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
