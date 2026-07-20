/**
 * Skyward SIS companion — READ path + counsel-blocked WRITE stubs.
 *
 * See docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md.
 */

export type SkywardPersonRow = {
  external_id?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  role?: "student" | "staff" | "guardian" | string;
};

/** Safe-read: parse directory printout HTML already open in the operator tab. */
export function extractSkyward(document: Document): SkywardPersonRow[] {
  const rows: SkywardPersonRow[] = [];
  const tables = Array.from(document.querySelectorAll("table"));
  for (const table of tables) {
    const trs = Array.from(table.querySelectorAll("tr"));
    for (const tr of trs.slice(1)) {
      const cells = Array.from(tr.querySelectorAll("td")).map((td) =>
        (td.textContent || "").trim(),
      );
      if (cells.length < 2) continue;
      rows.push({
        external_id: cells[0] || undefined,
        first_name: cells[1] || undefined,
        last_name: cells[2] || undefined,
        email: cells.find((c) => c.includes("@")),
        role: "student",
      });
    }
  }
  return rows;
}

// honest-stub: write-path counsel-blocked — module write surface
export async function writeSkywardPasswordReset(_opts: {
  accountId: string;
  newPassword: string;
}): Promise<never> {
  // honest-stub: write-path counsel-blocked
  throw new Error(
    "Skyward write-path blocked pending counsel signoff — see docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md",
  );
}

export async function writeSkywardEnrollmentChange(_opts: {
  studentId: string;
  status: string;
}): Promise<never> {
  // honest-stub: write-path counsel-blocked
  throw new Error(
    "Skyward write-path blocked pending counsel signoff — see docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md",
  );
}
