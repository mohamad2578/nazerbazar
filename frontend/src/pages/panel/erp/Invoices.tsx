import { useQuery } from "@tanstack/react-query";
import { FileText, Printer, Search } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Input, Loading, PageHeader, Select, useToast } from "../../../components/ui";
import { api, type Page } from "../../../lib/api";
import { printSalesInvoice, type InvoiceData } from "../../../lib/erp";
import { date, toman } from "../../../lib/format";
import { ORDER_TONE, PAY_TONE, type OrderT } from "../../../lib/orders";

/** بایگانی فاکتورهای فروش: جستجو بر اساس شماره فاکتور، نام یا موبایل مشتری و چاپ فاکتور رسمی. */
export default function Invoices() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const q = useQuery({
    queryKey: ["erp-invoices", search, status],
    queryFn: () => api.get<Page<OrderT>>("/orders/", { search, status, page_size: 60 }),
  });
  const print = async (o: OrderT) => {
    setBusy(o.id);
    try {
      const data = await api.get<InvoiceData>(`/orders/${o.id}/invoice/`);
      if (!printSalesInvoice(data)) toast("اجازه باز شدن پنجره جدید را بدهید", "danger");
    } catch (e) {
      toast((e as Error).message, "danger");
    } finally {
      setBusy(null);
    }
  };
  const rows = q.data?.results ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="فاکتورهای فروش" subtitle="هر سفارش یک فاکتور با شماره ترتیبی دارد؛ فاکتور رسمی (با مالیات و مبلغ به حروف) را چاپ یا PDF کنید." />
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative sm:w-72">
          <Search className="absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره فاکتور، نام یا موبایل مشتری" className="pr-9" />
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="sm:w-48">
          <option value="">همه وضعیت‌ها</option><option value="delivered">تحویل‌شده</option><option value="out_for_delivery">در مسیر</option>
          <option value="ready">آماده تحویل</option><option value="canceled">لغوشده</option>
        </Select>
      </div>
      {q.isLoading ? <Loading /> : !rows.length ? <Card><Empty title="فاکتوری پیدا نشد" icon={<FileText className="size-7" />} /></Card> : (
        <div className="space-y-2">
          {rows.map((o) => (
            <Card key={o.id} className="flex items-center justify-between gap-3 p-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <b dir="ltr">{o.invoice_no || o.code}</b>
                  <Badge tone={ORDER_TONE[o.status]}>{o.status_display}</Badge>
                  <Badge tone={PAY_TONE[o.payment_status]}>{o.payment_status_display}</Badge>
                </div>
                <div className="mt-0.5 truncate text-xs text-muted">{o.customer_name} · {date(o.created_at)} · {o.payment_method_display}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <b className="tabular text-sm">{toman(o.total)}</b>
                <Button size="sm" variant="secondary" loading={busy === o.id} icon={<Printer className="size-4" />} onClick={() => print(o)}>چاپ</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
