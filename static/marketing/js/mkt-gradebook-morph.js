/**
 * Fluid classroom gradebook morph.
 *
 * Back-compat: the original SVG column-emphasis behaviour is preserved for the
 * surfaces that use [data-mkt-framework-column]. When a [data-mkt-gradebook-table]
 * host is present, this ALSO renders a polymorphic gradebook 100% client-side:
 * the SAME student mastery (0–100) is re-expressed across US letters/GPA, IB 1–7,
 * Cambridge A*–G, and a local competency scale — same cell footprint every time,
 * so there is zero layout shift. No backend call.
 */
(function () {
  "use strict";

  // Same underlying record. mastery 0–100; never re-entered when frameworks switch.
  var SUBJECTS = ["Math", "Science", "English", "Arts"];
  var STUDENTS = [
    { name: "Amara Okeke", scores: [95, 88, 72, 84] },
    { name: "Liam Walsh", scores: [78, 91, 83, 60] },
    { name: "Mei Tanaka", scores: [89, 67, 94, 90] },
    { name: "Sofia Reyes", scores: [64, 75, 81, 58] }
  ];

  // band: 1..4 (drives the pill colour); label: framework-specific text.
  function express(score, framework) {
    var band = score >= 85 ? 4 : score >= 70 ? 3 : score >= 55 ? 2 : 1;
    var label;
    if (framework === "ib") {
      label = score >= 90 ? "7" : score >= 80 ? "6" : score >= 70 ? "5"
        : score >= 60 ? "4" : score >= 50 ? "3" : score >= 40 ? "2" : "1";
    } else if (framework === "caie") {
      label = score >= 90 ? "A*" : score >= 80 ? "A" : score >= 70 ? "B"
        : score >= 60 ? "C" : score >= 50 ? "D" : score >= 40 ? "E" : "U";
    } else if (framework === "competency") {
      label = score >= 85 ? "Mastery" : score >= 70 ? "Secure"
        : score >= 55 ? "Developing" : "Emerging";
    } else {
      // US letters + GPA
      var letter = score >= 93 ? "A" : score >= 90 ? "A-" : score >= 87 ? "B+"
        : score >= 83 ? "B" : score >= 80 ? "B-" : score >= 77 ? "C+"
        : score >= 73 ? "C" : score >= 70 ? "C-" : score >= 67 ? "D+" : "D";
      label = letter;
    }
    return { band: band, label: label };
  }

  function classAverageLabel(framework) {
    var all = STUDENTS.reduce(function (acc, s) { return acc.concat(s.scores); }, []);
    var avg = Math.round(all.reduce(function (a, b) { return a + b; }, 0) / all.length);
    if (framework === "us") {
      var gpa = (Math.min(4, Math.max(0, (avg - 60) / 10))).toFixed(1);
      return express(avg, "us").label + " · " + gpa + " GPA";
    }
    if (framework === "ib") return express(avg, "ib").label + " / 7";
    if (framework === "caie") return express(avg, "caie").label;
    return express(avg, "competency").label;
  }

  function initials(name) {
    return name.split(/\s+/).map(function (p) { return p.charAt(0); }).join("").slice(0, 2).toUpperCase();
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function renderTable(host, framework) {
    host.style.setProperty("--cols", String(SUBJECTS.length));
    host.textContent = "";

    // header row
    var head = el("div", "mkt-fc-grow");
    head.appendChild(el("div", "mkt-fc-ghead", "Student"));
    SUBJECTS.forEach(function (s) { head.appendChild(el("div", "mkt-fc-ghead", s)); });
    host.appendChild(head);

    // student rows
    STUDENTS.forEach(function (stu, i) {
      var row = el("div", "mkt-fc-grow");
      var who = el("div", "mkt-fc-student");
      who.appendChild(el("span", "mkt-fc-av mkt-fc-av--" + (i % 5), initials(stu.name)));
      who.appendChild(el("span", "mkt-fc-sname", stu.name));
      row.appendChild(who);
      stu.scores.forEach(function (sc) {
        var ex = express(sc, framework);
        row.appendChild(el("span", "mkt-fc-pill mkt-fc-pill--" + ex.band, ex.label));
      });
      host.appendChild(row);
    });
  }

  function setSvgFramework(root, framework) {
    var viz = root.querySelector("[data-mkt-gradebook-viz]");
    if (!viz) return;
    viz.querySelectorAll("[data-mkt-framework-column]").forEach(function (col) {
      var active = col.getAttribute("data-mkt-framework-column") === framework;
      col.classList.toggle("is-emphasized", active);
      col.classList.toggle("is-dimmed", !active);
    });
  }

  function init(root) {
    var tabs = root.querySelectorAll("[data-mkt-framework]");
    var table = root.querySelector("[data-mkt-gradebook-table]");
    var summary = root.querySelector("[data-mkt-gradebook-summary]");

    function apply(framework) {
      setSvgFramework(root, framework);
      if (table) renderTable(table, framework);
      if (summary) summary.textContent = classAverageLabel(framework);
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var framework = tab.getAttribute("data-mkt-framework");
        tabs.forEach(function (t) {
          t.classList.remove("is-active");
          t.setAttribute("aria-selected", "false");
        });
        tab.classList.add("is-active");
        tab.setAttribute("aria-selected", "true");
        apply(framework);
      });
    });

    var active = root.querySelector("[data-mkt-framework].is-active");
    apply(active ? active.getAttribute("data-mkt-framework") : "us");
  }

  document.querySelectorAll("[data-mkt-gradebook-morph]").forEach(init);
})();
