import { ImagePlus, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import { cx } from "./ui";

/** تصویر انتخابی را پیش از آپلود در مرورگر کوچک و فشرده می‌کند تا حجم فایل پایین بماند. */
export async function compressImage(file: File, max = 800, quality = 0.82): Promise<File> {
  if (!file.type.startsWith("image/")) return file;
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file;
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();
  const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", quality));
  if (!blob || blob.size >= file.size) return file;
  return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
}

type Props = {
  value?: string | null;
  onChange: (file: File | null) => void;
  /** نسبت قاب پیش‌نمایش، مثلا "1/1" یا "21/9" */
  aspect?: string;
  hint?: string;
  className?: string;
};

export default function ImageUpload({ value, onChange, aspect = "1/1", hint, className }: Props) {
  const [preview, setPreview] = useState<string | null>(value ?? null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      const small = await compressImage(file);
      setPreview(URL.createObjectURL(small));
      onChange(small);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <label
        className={cx(
          "relative flex cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-dashed border-line bg-surface-2",
          !preview && "hover:border-brand/50",
        )}
        style={{ aspectRatio: aspect }}
      >
        {preview ? (
          <img src={preview} alt="" className="size-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-sm text-muted">
            {busy ? <Loader2 className="size-6 animate-spin" /> : <ImagePlus className="size-6" />}
            {busy ? "در حال آماده‌سازی…" : "انتخاب تصویر"}
          </span>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </label>
      <div className="mt-1 flex items-center justify-between">
        <span className="text-xs text-muted">{hint ?? "تصویر پیش از ارسال به‌صورت خودکار فشرده می‌شود."}</span>
        {preview && (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-danger"
            onClick={() => {
              setPreview(null);
              onChange(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            <X className="size-3.5" /> حذف تصویر
          </button>
        )}
      </div>
    </div>
  );
}
