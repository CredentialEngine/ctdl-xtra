import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { EmailNotificationPreference, trpc } from "@/utils";
import { zodResolver } from "@hookform/resolvers/zod";
import { useContext, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useToast } from "@/components/ui/use-toast";
import UserContext from "@/userContext";

const FormSchema = z
  .object({
    password: z.string().min(6),
    passwordConfirmation: z.string().min(6),
  })
  .superRefine(({ password, passwordConfirmation }, ctx) => {
    if (password !== passwordConfirmation) {
      ctx.addIssue({
        code: "custom",
        message: "The passwords did not match",
        path: ["passwordConfirmation"],
      });
    }
  });

const emailNotificationPreferenceSchema = z.nativeEnum(
  EmailNotificationPreference
);

export default function MyProfile() {
  const { user } = useContext(UserContext);
  const userId = user?.id as number | undefined;
  const detailQuery = trpc.users.detail.useQuery(
    { id: userId! },
    { enabled: userId != null }
  );
  const patchPrefs = trpc.users.patchUserPreferences.useMutation();
  const redefPassword = trpc.users.redefinePassword.useMutation();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      password: "",
      passwordConfirmation: "",
    },
  });
  const { toast } = useToast();

  const savedNotificationPref =
    detailQuery.data?.userPreferences?.email?.notifications ??
    EmailNotificationPreference.ALWAYS;

  const [draftNotificationPref, setDraftNotificationPref] =
    useState<EmailNotificationPreference>(EmailNotificationPreference.ALWAYS);

  useEffect(() => {
    if (detailQuery.data) {
      setDraftNotificationPref(
        detailQuery.data.userPreferences?.email?.notifications ??
          EmailNotificationPreference.ALWAYS
      );
    }
  }, [detailQuery.data]);

  const notificationPrefsDirty =
    draftNotificationPref !== savedNotificationPref;

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    await redefPassword.mutateAsync({ password: data.password });
    toast({
      title: "Password redefinition",
      description: "Your password has been updated.",
    });
    form.reset();
  }

  return (
    <>
      <h1 className="text-lg font-semibold md:text-2xl">My Profile</h1>
      <div>
        <div className="w-full space-y-6">
          <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Email notifications</CardTitle>
                <CardDescription>
                  These emails cover finished extractions and recipe configuration
                  detection. Notify for my extractions limits mail to runs you
                  started and detection you triggered; choose Notify me always to
                  receive every notification from the app.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4">
                <RadioGroup
                  value={draftNotificationPref}
                  onValueChange={(value) => {
                    const parsed =
                      emailNotificationPreferenceSchema.safeParse(value);
                    if (parsed.success) {
                      setDraftNotificationPref(parsed.data);
                    }
                  }}
                  disabled={
                    detailQuery.isLoading ||
                    detailQuery.isFetching ||
                    patchPrefs.isLoading
                  }
                  className="grid gap-3"
                >
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem
                      value={EmailNotificationPreference.ALWAYS}
                      id="email-notify-always"
                    />
                    <Label htmlFor="email-notify-always" className="font-normal">
                      Notify me always
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem
                      value={EmailNotificationPreference.MINE}
                      id="email-notify-mine"
                    />
                    <Label htmlFor="email-notify-mine" className="font-normal">
                      Notify for my extractions
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem
                      value={EmailNotificationPreference.OFF}
                      id="email-notify-off"
                    />
                    <Label htmlFor="email-notify-off" className="font-normal">
                      Off
                    </Label>
                  </div>
                </RadioGroup>
                <Button
                  type="button"
                  className="w-[150px]"
                  disabled={
                    !notificationPrefsDirty ||
                    detailQuery.isLoading ||
                    patchPrefs.isLoading
                  }
                  onClick={async () => {
                    await patchPrefs.mutateAsync({
                      email: {
                        notifications: draftNotificationPref,
                      },
                    });
                    await detailQuery.refetch();
                    toast({
                      title: "Preferences saved",
                      description:
                        "Your email notification settings were updated.",
                    });
                  }}
                >
                  Save
                </Button>
              </CardContent>
            </Card>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)}>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Change password</CardTitle>
                    <CardDescription>
                      Set a new password for your account.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4">
                    <div className="grid gap-2">
                      <FormField
                        control={form.control}
                        name="password"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>New Password</FormLabel>
                            <FormControl>
                              <Input
                                placeholder="Your password"
                                type="password"
                                {...field}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                    <div className="grid gap-2">
                      <FormField
                        control={form.control}
                        name="passwordConfirmation"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>New Password Confirmation</FormLabel>
                            <FormControl>
                              <Input
                                placeholder="Confirm the password"
                                type="password"
                                {...field}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                    <Button
                      type="submit"
                      className="w-[150px]"
                      disabled={redefPassword.isLoading ? true : undefined}
                    >
                      Update password
                    </Button>
                  </CardContent>
                </Card>
              </form>
            </Form>
          </div>
        </div>
      </div>
    </>
  );
}
