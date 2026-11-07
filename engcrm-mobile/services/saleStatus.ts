// The life of a one-off sale (the server's gcrm/sale_status.py): only a collected
// sale is money won; expected, booked and contracted ones are the pipeline.
export type SaleStatus = "expected" | "booked" | "contracted" | "collected" | "cancelled";

export const SALE_STATUSES: SaleStatus[] = ["expected", "booked", "contracted", "collected", "cancelled"];
