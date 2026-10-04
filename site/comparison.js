/* Equal-duration listening comparisons, using only the public aggregate datasets. */
window.Origins = (() => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const number = (v) =>
    new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(v);
  const date = (s) =>
    new Date(s + "T12:00:00Z").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  let history,
    comparisons,
    windowDays = 90,
    active,
    thenSongs,
    nowSongs,
    chosenSong;
  const songKey = (id) =>
    history.tracks[id].artist + "\u0000" + history.tracks[id].title;
  function songs(rows) {
    const grouped = new Map();
    for (const [id, plays, ms] of rows) {
      const t = history.tracks[id],
        key = songKey(id);
      if (!grouped.has(key))
        grouped.set(key, {
          key,
          id,
          artist: t.artist,
          title: t.title,
          plays: 0,
          ms: 0,
        });
      const s = grouped.get(key);
      s.plays += plays;
      s.ms += ms;
    }
    return [...grouped.values()].sort(
      (a, b) =>
        b.plays - a.plays || b.ms - a.ms || a.title.localeCompare(b.title),
    );
  }
  const trackUrl = (s) =>
    "https://open.spotify.com/track/" + history.tracks[s.id].spotifyId;
  function render() {
    active = comparisons.windows.find((w) => w.days === windowDays);
    thenSongs = songs(active.then.tracks);
    nowSongs = songs(active.now.tracks);
    document.querySelectorAll("[data-window]").forEach((b) => {
      const on = Number(b.dataset.window) === windowDays;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
    const maxShare = Math.max(
      ...[active.then, active.now].flatMap((w, i) =>
        (i ? nowSongs : thenSongs)
          .slice(0, 5)
          .map((t) => (t.plays / w.plays) * 100),
      ),
      1,
    );
    $("#era-cards").innerHTML = [
      ["then", active.then, thenSongs],
      ["now", active.now, nowSongs],
    ]
      .map(([era, w, tracks]) => {
        const leader = tracks[0];
        return `<article class="era-card ${era}"><div class="era-card-top"><span class="era-label">${era === "then" ? "THEN" : "NOW"}</span><span>${era === "then" ? "Your first" : "The latest"} ${w.days} days</span></div><p class="era-dates">${date(w.start)} — ${date(w.end)}</p><div class="era-favorite"><span class="tiny-label">THE SONG ON REPEAT</span><a href="${trackUrl(leader)}" target="_blank" rel="noreferrer">${esc(leader.title)}</a><p>${esc(history.artists[leader.artist])}</p></div><div class="era-numbers"><div><strong>${number(w.plays)}</strong><span>plays</span></div><div><strong>${number(w.ms / 3600000)}</strong><span>hours</span></div><div><strong>${w.activeDays}<small>/${w.days}</small></strong><span>days with music</span></div></div><div class="era-tracklist"><div class="era-list-label"><span>TOP FIVE SONGS</span><span>SHARE OF PLAYS</span></div>${tracks
          .slice(0, 5)
          .map(
            (t, i) =>
              `<div class="era-song"><span class="rank">${String(i + 1).padStart(2, "0")}</span><div class="era-song-info"><a href="${trackUrl(t)}" target="_blank" rel="noreferrer">${esc(t.title)}</a><span>${esc(history.artists[t.artist])}</span><div class="era-song-bar"><i style="width:${(((t.plays / w.plays) * 100) / maxShare) * 100}%"></i></div></div><div class="era-song-count">${number((t.plays / w.plays) * 100)}%<small>${t.plays} plays</small></div></div>`,
          )
          .join("")}</div></article>`;
      })
      .join("");
    const ratio = active.now.ms / active.then.ms;
    $("#comparison-insight").innerHTML =
      `Music filled <strong>${active.then.activeDays} of ${windowDays} days then</strong>, and <strong>${active.now.activeDays} of ${windowDays} days now</strong>. ${ratio >= 1 ? `You listened for <strong>${number(ratio)}× as long</strong>` : `Listening time was <strong>${number((1 - ratio) * 100)}% lower</strong>`} in the latest window.`;
    renderShifts();
    renderReturning();
    const options = thenSongs;
    if (!options.some((t) => t.key === chosenSong))
      chosenSong = options[0]?.key;
    $("#memory-song").innerHTML = options
      .map(
        (t) =>
          `<option value="${t.id}">${esc(t.title)} · ${esc(history.artists[t.artist])}</option>`,
      )
      .join("");
    const chosen = options.find((t) => t.key === chosenSong);
    $("#memory-song").value = chosen?.id;
    renderMemory();
    $("#comparison-method").textContent =
      `The first window runs ${date(active.then.start)}–${date(active.then.end)}; the latest runs ${date(active.now.start)}–${date(active.now.end)}. Each contains exactly ${windowDays} days. The archive starts ${date(comparisons.meta.start)}; it does not tell us when the account was created. “Now” ends on ${date(comparisons.meta.end)}, the latest date in this export, not live Spotify activity. This section has its own period controls and always ranks by play count.`;
  }
  function renderShifts() {
    const old = new Map(active.then.artists.map((a) => [a[0], a[1]])),
      recent = new Map(active.now.artists.map((a) => [a[0], a[1]]));
    const ids = new Set(
      [
        ...active.then.artists.slice(0, 5),
        ...active.now.artists.slice(0, 5),
      ].map((a) => a[0]),
    );
    const rows = [...ids]
      .map((id) => ({
        id,
        a: ((old.get(id) || 0) / active.then.plays) * 100,
        b: ((recent.get(id) || 0) / active.now.plays) * 100,
      }))
      .sort((a, b) => Math.abs(b.b - b.a) - Math.abs(a.b - a.a));
    const max = Math.max(...rows.flatMap((r) => [r.a, r.b]), 1) * 1.12;
    $("#artist-shifts").innerHTML = rows
      .map(
        (r) =>
          `<div class="shift-row"><span class="shift-name">${esc(history.artists[r.id])}</span><div class="shift-plot" role="img" aria-label="${esc(history.artists[r.id])}: ${number(r.a)} percent then, ${number(r.b)} percent now"><i class="shift-line" style="left:${(Math.min(r.a, r.b) / max) * 100}%;width:${(Math.abs(r.b - r.a) / max) * 100}%"></i><i class="shift-dot then-dot" style="left:${(r.a / max) * 100}%"></i><i class="shift-dot now-dot" style="left:${(r.b / max) * 100}%"></i></div><span class="shift-values"><b>${number(r.a)}%</b><span>→</span><b>${number(r.b)}%</b></span></div>`,
      )
      .join("");
  }
  function renderReturning() {
    const original = new Set(thenSongs.map((s) => s.key)),
      returning = nowSongs.filter((s) => original.has(s.key)),
      plays = returning.reduce((s, t) => s + t.plays, 0),
      share = (plays / active.now.plays) * 100;
    $("#return-share").textContent = number(share) + "%";
    $("#return-label").textContent =
      "of your latest plays were songs from the beginning";
    $("#return-bar").innerHTML = `<span style="width:${share}%"></span>`;
    $("#return-bar").setAttribute(
      "aria-label",
      `${number(share)} percent of latest plays on songs heard in the first ${windowDays} days; ${number(100 - share)} percent on other songs.`,
    );
    $("#return-caption").textContent =
      `${returning.length} songs appear in both windows. They account for ${plays} of ${number(active.now.plays)} recent plays.`;
    $("#return-tracks").innerHTML = returning.length
      ? returning
          .slice(0, 4)
          .map((s) => {
            const t = thenSongs.find((t) => t.key === s.key);
            return `<a class="return-song" href="${trackUrl(s)}" target="_blank" rel="noreferrer"><div><strong>${esc(s.title)}</strong><span>${esc(history.artists[s.artist])}</span></div><div><b>${t.plays}</b><i>→</i><b>${s.plays}</b><small>plays, then / now</small></div></a>`;
          })
          .join("")
      : '<p class="comparison-caption">No songs from the first window reappear in the latest one.</p>';
  }
  function renderMemory() {
    const s = thenSongs.find((s) => s.key === chosenSong);
    if (!s) return;
    const matchIds = new Set(
      history.tracks
        .map((t, i) => (songKey(i) === s.key ? i : -1))
        .filter((i) => i >= 0),
    );
    const points = history.months.map((m) => ({
      month: m.month,
      plays: m.tracks.reduce(
        (sum, [id, p]) => sum + (matchIds.has(id) ? p : 0),
        0,
      ),
    }));
    const latest = nowSongs.find((t) => t.key === s.key),
      total = points.reduce((sum, p) => sum + p.plays, 0),
      peak = points.reduce((a, b) => (b.plays > a.plays ? b : a)),
      heard = points.filter((p) => p.plays > 0),
      years = new Set(heard.map((p) => p.month.slice(0, 4)));
    const link = $("#memory-link");
    link.textContent = s.title + " · " + history.artists[s.artist];
    link.href = trackUrl(s);
    $("#memory-compare").textContent =
      `${s.plays} plays then / ${latest?.plays || 0} now`;
    const node = $("#memory-chart"),
      W = Math.max(310, node.parentElement.clientWidth),
      H = 205,
      margin = { left: 30, right: 7, top: 18, bottom: 31 };
    const svg = d3.select(node);
    svg.selectAll("*").remove();
    svg
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr(
        "aria-label",
        `Monthly plays for ${s.title} by ${history.artists[s.artist]}. Use left and right arrows to explore the months.`,
      );
    const x = d3
        .scaleBand()
        .domain(points.map((p) => p.month))
        .range([margin.left, W - margin.right])
        .padding(0.2),
      y = d3
        .scaleLinear()
        .domain([0, Math.max(peak.plays, 1)])
        .nice()
        .range([H - margin.bottom, margin.top]);
    const ticks = y.ticks(3).filter(Number.isInteger);
    ticks.forEach((t) => {
      svg
        .append("line")
        .attr("x1", margin.left)
        .attr("x2", W - margin.right)
        .attr("y1", y(t))
        .attr("y2", y(t))
        .attr("stroke", "#35402c")
        .attr("stroke-dasharray", "2 4");
      svg
        .append("text")
        .attr("x", margin.left - 8)
        .attr("y", y(t) + 4)
        .attr("text-anchor", "end")
        .attr("font-size", 11)
        .attr("fill", "#a4b390")
        .text(t);
    });
    const yearLabels = points.filter(
      (p, i) => i === 0 || p.month.endsWith("-01"),
    );
    yearLabels
      .filter((p, i) => W > 480 || i % 2 === 0 || i === yearLabels.length - 1)
      .forEach((p) =>
        svg
          .append("text")
          .attr("x", x(p.month))
          .attr("y", H - 7)
          .attr("font-size", 11)
          .attr("fill", "#9eac8b")
          .text(p.month.slice(0, 4)),
      );
    const bars = svg
      .append("g")
      .selectAll("rect")
      .data(points)
      .join("rect")
      .attr("x", (p) => x(p.month))
      .attr("y", (p) => y(p.plays))
      .attr("width", x.bandwidth())
      .attr("height", (p) => Math.max(p.plays ? 2 : 1, y(0) - y(p.plays)))
      .attr("rx", 1)
      .attr("fill", (p) => (p.plays === peak.plays ? "#dcf88b" : "#aca4e6"))
      .attr("tabindex", (p, i) => (i === 0 ? 0 : -1))
      .attr("role", "img")
      .attr(
        "aria-label",
        (p) => `${date(p.month + "-01").replace(" 1,", ",")}: ${p.plays} plays`,
      );
    bars
      .on("pointermove", (e, p) => showMonth(e, p))
      .on("pointerleave", hideMonth)
      .on("focus", (e, p) => {
        const b = e.target.getBoundingClientRect();
        showMonth({ clientX: b.x, clientY: b.y }, p);
      })
      .on("blur", hideMonth)
      .on("keydown", (e, p) => {
        if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        const i = points.indexOf(p),
          next =
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? points.length - 1
                : Math.max(
                    0,
                    Math.min(
                      points.length - 1,
                      i + (e.key === "ArrowRight" ? 1 : -1),
                    ),
                  );
        const nodes = bars.nodes();
        e.target.setAttribute("tabindex", "-1");
        nodes[next].setAttribute("tabindex", "0");
        nodes[next].focus();
      })
      .append("title")
      .text((p) => `${p.month}: ${p.plays} plays`);
    const last = heard.at(-1),
      periodDesc =
        years.size === history.meta.years.length
          ? "every year in the archive"
          : `${years.size} of ${history.meta.years.length} calendar years`;
    $("#memory-caption").innerHTML =
      `<strong>${number(total)} plays</strong> across ${periodDesc}. It peaked in <strong>${new Date(peak.month + "-01T12:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}</strong> (${peak.plays} plays)${latest ? ` and appears <strong>${latest.plays} times</strong> in your latest ${windowDays} days` : `; last heard in <strong>${new Date(last.month + "-01T12:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}</strong>`}.`;
    let previous = -1,
      longestGap = 0,
      returned = null;
    points.forEach((point, i) => {
      if (!point.plays) return;
      if (previous >= 0 && i - previous - 1 > longestGap) {
        longestGap = i - previous - 1;
        returned = point.month;
      }
      previous = i;
    });
    if (longestGap >= 6) {
      const returnedMonth = new Date(
        returned + "-01T12:00Z",
      ).toLocaleDateString("en-US", {
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      });
      $("#memory-caption").innerHTML +=
        ` Its longest gap in recorded plays lasted <strong>${longestGap} full months</strong>, before a return in <strong>${returnedMonth}</strong>.`;
    }
  }
  function showMonth(e, p) {
    const tip = $("#tooltip");
    tip.innerHTML = `<strong>${date(p.month + "-01").replace(" 1,", ",")}</strong>${p.plays} plays`;
    tip.hidden = false;
    const b = tip.getBoundingClientRect();
    tip.style.left =
      Math.max(8, Math.min(e.clientX + 12, innerWidth - b.width - 12)) + "px";
    tip.style.top =
      Math.max(8, Math.min(e.clientY + 12, innerHeight - b.height - 12)) + "px";
  }
  function hideMonth() {
    $("#tooltip").hidden = true;
  }
  async function init(publicHistory) {
    try {
      history = publicHistory;
      const res = await fetch("data/comparison.json");
      if (!res.ok) throw new Error("Comparison archive unavailable");
      comparisons = await res.json();
      $("#first-day-date").textContent = date(comparisons.firstDay.date);
      const first = songs(comparisons.firstDay.tracks);
      $("#first-day-tracks").innerHTML = first
        .slice(0, 4)
        .map(
          (s) =>
            `<a href="${trackUrl(s)}" target="_blank" rel="noreferrer">${esc(s.title)}<span>${esc(history.artists[s.artist])} · ${s.plays} ${s.plays === 1 ? "play" : "plays"}</span></a>`,
        )
        .join("");
      document.querySelectorAll("[data-window]").forEach(
        (b) =>
          (b.onclick = () => {
            windowDays = Number(b.dataset.window);
            hideMonth();
            render();
          }),
      );
      $("#memory-song").onchange = (e) => {
        chosenSong = songKey(Number(e.target.value));
        renderMemory();
      };
      $("#origins-loading").hidden = true;
      $("#origins-content").hidden = false;
      render();
      // Resolve deep links after both datasets have populated the page layout.
      const target = document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView({ behavior: "instant", block: "start" });
      let timer;
      window.addEventListener("resize", () => {
        clearTimeout(timer);
        timer = setTimeout(renderMemory, 120);
      });
    } catch (e) {
      $("#origins-loading").textContent =
        "The time capsule couldn’t load. Refresh to try again.";
      console.error(e);
    }
  }
  return { init };
})();
