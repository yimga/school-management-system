/**
 * Enterprise constellation — interactive org nodes + wallet rollup highlight.
 */
(function () {
  "use strict";

  var COPY = {
    holdco: {
      title: "HoldCo / Diocese",
      body: "One parent org · many institution types · unified login profile.",
      roles: ["Teacher @ K-12 cluster", "Student @ university", "IT admin @ HoldCo"],
    },
    k12: {
      title: "K-12 cluster",
      body: "12 schools · shared admissions · localized fee rails.",
      roles: ["Homeroom teacher", "Registrar", "Parent portal"],
    },
    polytechnic: {
      title: "Technical college",
      body: "CTE programs · workforce credentials · separate sub-ledger.",
      roles: ["Instructor", "Work-study coordinator"],
    },
    university: {
      title: "University",
      body: "Higher-ed modules · research grants · cross-enrollment.",
      roles: ["Grad student", "Department chair", "Bursar"],
    },
    user: {
      title: "Unified identity",
      body: "One global profile · scoped permissions per institution.",
      roles: ["SSO · MFA · role graph"],
    },
  };

  function init(root) {
    var detail = root.querySelector("[data-mkt-enterprise-detail]");
    var graph = root.querySelector("[data-mkt-enterprise-graph]");
    var wallets = root.querySelectorAll("[data-wallet]");
    var rollup = root.querySelector("[data-mkt-enterprise-rollup]");

    function showNode(key) {
      var data = COPY[key] || COPY.holdco;
      if (!detail) return;
      detail.querySelector(".mkt-ve-enterprise__detail-title").textContent = data.title;
      detail.querySelector(".mkt-ve-enterprise__detail-body").textContent = data.body;
      var ul = detail.querySelector(".mkt-ve-enterprise__roles");
      if (ul) {
        ul.innerHTML = data.roles
          .map(function (r) {
            return "<li>" + r + "</li>";
          })
          .join("");
      }
    }

    if (graph) {
      graph.querySelectorAll("[data-mkt-enterprise-node]").forEach(function (node) {
        node.style.cursor = "pointer";
        node.addEventListener("click", function () {
          showNode(node.getAttribute("data-mkt-enterprise-node") || "holdco");
        });
      });
    }

    wallets.forEach(function (li, i) {
      li.addEventListener("mouseenter", function () {
        wallets.forEach(function (w) {
          w.classList.remove("is-active");
        });
        li.classList.add("is-active");
        if (rollup) rollup.textContent = "HoldCo rollup · wallet " + (i + 1) + " highlighted (illustrative)";
      });
    });

    showNode("holdco");
  }

  document.querySelectorAll("[data-mkt-enterprise-constellation]").forEach(init);
})();
