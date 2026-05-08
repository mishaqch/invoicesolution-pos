import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoginForm } from "@/features/auth/LoginForm";
import { useAuthStore } from "@/stores/auth";

export default function LoginRoute() {
  const access = useAuthStore((s) => s.access);
  const navigate = useNavigate();

  useEffect(() => {
    if (access) navigate("/", { replace: true });
  }, [access, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>Pakistan POS — admin dashboard</CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </div>
  );
}
