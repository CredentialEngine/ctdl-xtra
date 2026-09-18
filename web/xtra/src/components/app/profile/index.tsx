"use client";

import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useXtraAuth } from "../../../../app/components/auth/AuthProvider";

export default function MyProfile() {
    const { user } = useXtraAuth();

    return (
        <>
            <h1 className="text-lg font-semibold md:text-2xl">My Profile</h1>
            <div className="w-full max-w-2xl">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">
                            Keycloak identity
                        </CardTitle>
                        <CardDescription>
                            Authentication and password management are handled
                            by Keycloak.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 text-sm">
                        <div>
                            <span className="font-medium">Name:</span>{" "}
                            {user?.name || "—"}
                        </div>
                        <div>
                            <span className="font-medium">Email:</span>{" "}
                            {user?.email || "—"}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </>
    );
}
