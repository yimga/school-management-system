/* RMC Lexicon helper (Wave A — G1).
 *
 * Exposes `window.RMC.term(key, opts?)` so client-side templates / dynamic
 * components can render tenant-renamed terms ("Student" → "Scholar") in the
 * same shape Django's `{% term %}` tag produces server-side.
 *
 * Source of truth: <meta name="rmc-lexicon" content='{"student":{"s":"Scholar","p":"Scholars"}}'>.
 * Only keys that differ from the registry default are emitted, so the
 * helper carries its own fallback table for unsurprising rendering when
 * the tenant is on platform defaults (or anonymous).
 *
 * No global namespace pollution beyond `window.RMC.term` and `window.RMC.lexicon`.
 */
(function () {
  "use strict";

  // Defaults mirror the canonical Python registry (lexicon_catalog.py).
  // Keep this list in sync — when a key is added in Python, mirror it here so
  // anonymous / default-tenant rendering stays correct without the meta tag.
  var DEFAULTS = {
    student: { s: "Student", p: "Students" },
    teacher: { s: "Teacher", p: "Teachers" },
    parent: { s: "Parent", p: "Parents" },
    guardian: { s: "Guardian", p: "Guardians" },
    principal: { s: "Principal", p: "Principals" },
    head_teacher: { s: "Head teacher", p: "Head teachers" },
    administrator: { s: "Administrator", p: "Administrators" },
    staff: { s: "Staff member", p: "Staff" },
    alumnus: { s: "Alumnus", p: "Alumni" },
    counsellor: { s: "Counsellor", p: "Counsellors" },
    class: { s: "Class", p: "Classes" },
    course: { s: "Course", p: "Courses" },
    subject: { s: "Subject", p: "Subjects" },
    lesson: { s: "Lesson", p: "Lessons" },
    module: { s: "Module", p: "Modules" },
    assignment: { s: "Assignment", p: "Assignments" },
    exam: { s: "Exam", p: "Exams" },
    quiz: { s: "Quiz", p: "Quizzes" },
    project: { s: "Project", p: "Projects" },
    homework: { s: "Homework", p: "Homework" },
    school: { s: "School", p: "Schools" },
    campus: { s: "Campus", p: "Campuses" },
    department: { s: "Department", p: "Departments" },
    classroom: { s: "Classroom", p: "Classrooms" },
    dormitory: { s: "Dormitory", p: "Dormitories" },
    library: { s: "Library", p: "Libraries" },
    term: { s: "Term", p: "Terms" },
    semester: { s: "Semester", p: "Semesters" },
    academic_year: { s: "Academic year", p: "Academic years" },
    period: { s: "Period", p: "Periods" },
    session: { s: "Session", p: "Sessions" },
    grade: { s: "Grade", p: "Grades" },
    gpa: { s: "GPA", p: "GPAs" },
    report_card: { s: "Report card", p: "Report cards" },
    transcript: { s: "Transcript", p: "Transcripts" },
    attendance: { s: "Attendance", p: "Attendance" },
    announcement: { s: "Announcement", p: "Announcements" },
    message: { s: "Message", p: "Messages" },
    notice: { s: "Notice", p: "Notices" },
    fee: { s: "Fee", p: "Fees" },
    invoice: { s: "Invoice", p: "Invoices" },
  };

  function readOverrides() {
    var meta = document.querySelector('meta[name="rmc-lexicon"]');
    if (!meta) {
      return {};
    }
    var raw = meta.getAttribute("content");
    if (!raw) {
      return {};
    }
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  var overrides = readOverrides();

  function autoPlural(singular) {
    if (!singular) return singular;
    var last = singular.charAt(singular.length - 1).toLowerCase();
    if (last === "s") return singular;
    if (
      last === "y" &&
      singular.length >= 2 &&
      "aeiou".indexOf(singular.charAt(singular.length - 2).toLowerCase()) === -1
    ) {
      return singular.slice(0, -1) + "ies";
    }
    return singular + "s";
  }

  function resolveOne(key, plural) {
    var slot = overrides[key] || DEFAULTS[key];
    if (!slot) {
      return plural ? autoPlural(key) : key;
    }
    if (plural) {
      if (slot.p) return slot.p;
      // Override may have set only the singular; derive plural.
      var defaultSlot = DEFAULTS[key];
      if (defaultSlot && slot.s === defaultSlot.s) return defaultSlot.p;
      return autoPlural(slot.s || key);
    }
    return slot.s || (DEFAULTS[key] && DEFAULTS[key].s) || key;
  }

  function term(key, opts) {
    if (!key) return "";
    var options = opts || {};
    var resolved = resolveOne(String(key), Boolean(options.plural));
    if (options.capitalize && resolved) {
      return resolved.charAt(0).toUpperCase() + resolved.slice(1);
    }
    if (options.lower && resolved) {
      return resolved.toLowerCase();
    }
    return resolved;
  }

  function snapshot() {
    var out = {};
    var keys = Object.keys(DEFAULTS);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      out[key] = {
        singular: resolveOne(key, false),
        plural: resolveOne(key, true),
      };
    }
    return out;
  }

  var ns = (window.RMC = window.RMC || {});
  ns.term = term;
  ns.lexicon = {
    snapshot: snapshot,
    overrides: function () {
      return overrides;
    },
    refresh: function () {
      overrides = readOverrides();
    },
  };
})();
