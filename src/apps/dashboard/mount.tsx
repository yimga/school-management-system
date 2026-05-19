import { createRoot } from "react-dom/client";
import { TenantOverview } from "./TenantOverview";

function mountTenantOverviews(): void {
  const nodes = document.querySelectorAll<HTMLElement>("[data-rmc-tenant-overview]");
  nodes.forEach((el) => {
    const tenantId = el.getAttribute("data-tenant-id")?.trim() || "demo-school";
    const apiUrl = el.getAttribute("data-api-url")?.trim() || undefined;
    const useSeeder = el.getAttribute("data-use-seeder") === "1";
    const corrupt = el.getAttribute("data-corrupt-revenue") === "1";
    createRoot(el).render(
      <TenantOverview
        tenantId={tenantId}
        apiUrl={apiUrl}
        simulateAsync={false}
        corruptRevenue={corrupt}
        useSeeder={useSeeder}
      />,
    );
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountTenantOverviews);
} else {
  mountTenantOverviews();
}
