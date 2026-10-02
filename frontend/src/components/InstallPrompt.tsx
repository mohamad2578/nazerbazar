import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

/** پیشنهاد نصب نسخه PWA روی صفحه اصلی گوشی */
export default function InstallPrompt() {
  const [evt, setEvt] = useState<BIPEvent | null>(null);
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem("nb.install.dismissed") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    const on = (e: Event) => {
      e.preventDefault();
      setEvt(e as BIPEvent);
    };
    window.addEventListener("beforeinstallprompt", on);
    return () => window.removeEventListener("beforeinstallprompt", on);
  }, []);
  if (!evt || hidden) return null;
  const dismiss = () => {
    setHidden(true);
    try {
      localStorage.setItem("nb.install.dismissed", "1");
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="fixed inset-x-3 bottom-20 z-[700] mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-line bg-surface p-3 shadow-lg lg:bottom-6">
      <img src="/icon.svg" alt="" className="size-10" />
      <div className="flex-1 text-sm">
        <div className="font-medium">نصب ناظر بازار</div>
        <div className="text-xs text-muted">دسترسی سریع از صفحه اصلی گوشی، حتی با اینترنت ضعیف</div>
      </div>
      <button
        onClick={async () => {
          await evt.prompt();
          setEvt(null);
        }}
        className="inline-flex h-9 items-center gap-1 rounded-xl bg-brand px-3 text-sm text-brand-ink"
      >
        <Download className="size-4" /> نصب
      </button>
      <button onClick={dismiss} aria-label="بستن" className="text-muted">
        <X className="size-5" />
      </button>
    </div>
  );
}
