import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

import type { AuthResponse } from "@pos/shared/types";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Required."),
});
type FormValues = z.infer<typeof schema>;

export function LoginForm() {
  const navigate = useNavigate();
  const signIn = useAuthStore((s) => s.signIn);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      const resp = await api<AuthResponse>(
        "/auth/login/",
        { method: "POST", body: JSON.stringify(values) },
        { auth: false },
      );
      // Reject the session when tenant=null. Two reasons that's true:
      //   A) The user is platform-staff (super-admin operator). They
      //      should sign in at /admin/, not here.
      //   B) The user is a tenant user but has no active membership
      //      yet — the super-admin forgot to wire them up. Show a
      //      different message so the operator knows what to fix.
      if (!resp.tenant) {
        if (resp.user?.is_platform_staff) {
          setSubmitError(
            "This account is a platform / super-admin account — it cannot sign in to the tenant admin. Use the super-admin at http://localhost:8000/admin/ instead.",
          );
        } else {
          setSubmitError(
            "This account has no active tenant. Ask your platform administrator to add a tenant membership before you can sign in.",
          );
        }
        return;
      }
      signIn(resp);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSubmitError("Wrong email or password.");
      } else if (err instanceof ApiError && err.status === 429) {
        setSubmitError("Too many attempts. Wait a few minutes and try again.");
      } else {
        setSubmitError("Something went wrong. Please try again.");
      }
    }
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          autoFocus
          {...register("email")}
        />
        {errors.email && (
          <p className="text-xs text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          {...register("password")}
        />
        {errors.password && (
          <p className="text-xs text-destructive">{errors.password.message}</p>
        )}
      </div>

      {submitError && <p className="text-sm text-destructive">{submitError}</p>}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
