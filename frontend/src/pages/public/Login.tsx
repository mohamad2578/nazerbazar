import { KeyRound, Smartphone, UserPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, Field, Input, Segmented } from "../../components/ui";
import { api, ApiError, fieldErrors } from "../../lib/api";
import { isPanelUser, useAuth, type Me } from "../../lib/auth";
import { num, toEn } from "../../lib/format";

type TokenResp = { access: string; refresh: string; user: Me };

export default function Login() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const next = params.get("next");
  const [mode, setMode] = useState<"otp" | "password" | "register">("register");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [regErrors, setRegErrors] = useState<Record<string, string>>({});
  const [mobile, setMobile] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"mobile" | "code">("mobile");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [timer, setTimer] = useState(0);
  const [hint, setHint] = useState("");
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (timer <= 0) return;
    const t = setTimeout(() => setTimer(timer - 1), 1000);
    return () => clearTimeout(t);
  }, [timer]);

  if (user) return <Navigate to={next || (isPanelUser(user) ? "/panel" : "/account")} replace />;

  const done = (r: TokenResp) => {
    login(r);
    nav(next || (isPanelUser(r.user) ? "/panel" : "/"), { replace: true });
  };

  const run = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "ارتباط با سرور برقرار نشد.");
    } finally {
      setBusy(false);
    }
  };

  const send = () =>
    run(async () => {
      const r = await api.post<{ ttl: number; debug_code?: string }>("/auth/otp/request/", { mobile: toEn(mobile) });
      setStep("code");
      setTimer(r.ttl);
      setHint(r.debug_code ? `کد آزمایشی: ${r.debug_code}` : "");
      setTimeout(() => codeRef.current?.focus(), 50);
    });

  const verify = (c = code) => run(async () => done(await api.post<TokenResp>("/auth/otp/verify/", { mobile: toEn(mobile), code: toEn(c) })));

  return (
    <div className="mx-auto max-w-md py-4">
      <Card className="p-6">
        <h1 className="text-xl font-bold">ورود به ناظر بازار</h1>
        <p className="mt-1 text-sm text-muted">شهروندان، فروشگاه‌ها و کاربران سازمانی</p>
        <div className="mt-5">
          <Segmented
            value={mode}
            onChange={(m) => {
              setMode(m);
              setError("");
            }}
            options={[
              { value: "register", label: <span className="inline-flex items-center gap-1"><UserPlus className="size-4" /> ثبت‌نام</span> },
              { value: "password", label: <span className="inline-flex items-center gap-1"><KeyRound className="size-4" /> رمز عبور</span> },
              { value: "otp", label: <span className="inline-flex items-center gap-1"><Smartphone className="size-4" /> کد پیامکی</span> },
            ]}
          />
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === "register") {
              setRegErrors({});
              run(async () => {
                try {
                  done(await api.post<TokenResp>("/auth/register/", { mobile: toEn(mobile), password, first_name: firstName, last_name: lastName }));
                } catch (err) {
                  if (err instanceof ApiError) setRegErrors(fieldErrors(err));
                  throw err;
                }
              });
            }
            else if (mode === "password") run(async () => done(await api.post<TokenResp>("/auth/login/", { mobile: toEn(mobile), password })));
            else if (step === "mobile") send();
            else verify();
          }}
        >
          <Field label="شماره موبایل">
            <Input
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
              inputMode="tel"
              autoComplete="tel"
              placeholder="۰۹۱۲۳۴۵۶۷۸۹"
              dir="ltr"
              className="text-left"
              disabled={mode === "otp" && step === "code"}
              required
            />
          </Field>
          {mode === "otp" && step === "code" && (
            <Field
              label="کد تایید"
              hint={
                <span className="flex justify-between">
                  <span>{hint || `کد به ${mobile} ارسال شد`}</span>
                  {timer > 0 ? (
                    <span className="tabular">{num(Math.floor(timer / 60))}:{num(timer % 60).padStart(2, "۰")}</span>
                  ) : (
                    <button type="button" onClick={send} className="text-brand">ارسال مجدد</button>
                  )}
                </span>
              }
            >
              <Input
                ref={codeRef}
                value={code}
                onChange={(e) => {
                  const v = toEn(e.target.value).replace(/\D/g, "").slice(0, 6);
                  setCode(v);
                  if (v.length === 5) verify(v);
                }}
                inputMode="numeric"
                autoComplete="one-time-code"
                dir="ltr"
                className="text-center text-lg tracking-[.5em]"
                maxLength={6}
              />
            </Field>
          )}
          {mode === "register" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Field label="نام" error={regErrors.first_name}>
                  <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="given-name" required />
                </Field>
                <Field label="نام خانوادگی" error={regErrors.last_name}>
                  <Input value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="family-name" required />
                </Field>
              </div>
              <Field label="رمز عبور" error={regErrors.password} hint="حداقل ۸ کاراکتر؛ با همین شماره و رمز وارد می‌شوید.">
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" dir="ltr" required />
              </Field>
            </>
          )}
          {mode === "password" && (
            <Field label="رمز عبور">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" dir="ltr" required />
            </Field>
          )}
          {error && <p className="rounded-xl bg-danger-soft p-3 text-sm text-danger">{error}</p>}
          <Button type="submit" loading={busy} className="w-full" size="lg">
            {mode === "register" ? "ثبت‌نام و ورود" : mode === "password" ? "ورود" : step === "mobile" ? "دریافت کد تایید" : "تایید و ورود"}
          </Button>
          {mode === "otp" && step === "code" && (
            <button type="button" onClick={() => { setStep("mobile"); setCode(""); }} className="w-full text-sm text-muted">
              تغییر شماره موبایل
            </button>
          )}
        </form>
      </Card>
    </div>
  );
}
