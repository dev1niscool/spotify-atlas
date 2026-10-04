"use strict";
const $ = (s) => document.querySelector(s);
const palette = [
  "#e6a77d",
  "#d8ee90",
  "#aca4e6",
  "#e98279",
  "#82bba9",
  "#e6cb74",
  "#879dce",
  "#cb94b3",
  "#b4cc98",
  "#c3c5b3",
];
let data,
  selectedYear = "all",
  metric = "ms",
  chartMode = "flow",
  includeOther = false,
  selectedArtist = null,
  trackLimit = 7,
  current;
const fmt = new Intl.NumberFormat("en-US");
const escapeHtml = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const n = (v) => fmt.format(Math.round(v));
const amount = (item) => (metric === "ms" ? item.ms : item.plays);
const units = (v, short = false) =>
  metric === "ms"
    ? `${n(v / (short ? 3600000 : 60000))} ${short ? "hrs" : "min"}`
    : `${n(v)} plays`;
const fullMonth = (m) =>
  new Date(m + "-01T12:00:00Z").toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
const fullDate = (d) =>
  new Date(d + "T12:00:00Z").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
const color = (id) =>
  current?.colorMap?.get(id) ||
  palette[(data.colorOrder.get(id) ?? 0) % palette.length];
function tooltip(event, html) {
  const t = $("#tooltip");
  t.innerHTML = html;
  t.hidden = false;
  const box = t.getBoundingClientRect();
  t.style.left =
    Math.max(8, Math.min(event.clientX + 16, innerWidth - box.width - 12)) +
    "px";
  t.style.top =
    Math.max(8, Math.min(event.clientY + 14, innerHeight - box.height - 12)) +
    "px";
}
function hideTooltip() {
  $("#tooltip").hidden = true;
}
function aggregate(months) {
  const artists = new Map(),
    tracks = new Map();
  let plays = 0,
    ms = 0;
  for (const m of months) {
    plays += m.plays;
    ms += m.ms;
    for (const [id, p, t] of m.artists) {
      if (!artists.has(id)) artists.set(id, { id, plays: 0, ms: 0 });
      const a = artists.get(id);
      a.plays += p;
      a.ms += t;
    }
    for (const [id, p, t] of m.tracks) {
      if (!tracks.has(id)) tracks.set(id, { id, plays: 0, ms: 0 });
      const a = tracks.get(id);
      a.plays += p;
      a.ms += t;
    }
  }
  return {
    months,
    plays,
    ms,
    artists: [...artists.values()].sort((a, b) => amount(b) - amount(a)),
    tracks: [...tracks.values()].sort((a, b) => amount(b) - amount(a)),
  };
}
function periodName() {
  return selectedYear === "all" ? "The whole collection" : selectedYear;
}
function setYear(year) {
  selectedYear = String(year);
  selectedArtist = null;
  trackLimit = 7;
  $("#track-search").value = "";
  if (year !== "all") $("#calendar-year").value = year;
  render();
}
function render() {
  hideTooltip();
  const months = data.months.filter(
    (m) => selectedYear === "all" || m.month.startsWith(selectedYear),
  );
  current = aggregate(months);
  current.colorMap = new Map();
  const used = new Set();
  current.artists.slice(0, 10).forEach((a) => {
    let index = (data.colorOrder.get(a.id) || 0) % 10;
    while (used.has(index)) index = (index + 1) % 10;
    used.add(index);
    current.colorMap.set(a.id, palette[index]);
  });
  document.querySelectorAll("#years button").forEach((b) => {
    const on = b.dataset.year === selectedYear;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  document.querySelectorAll("[data-metric]").forEach((b) => {
    const on = b.dataset.metric === metric;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  $("#stat-hours").textContent = n(current.ms / 3600000);
  $("#stat-plays").textContent = n(current.plays);
  $("#stat-artists").textContent = n(current.artists.length);
  $("#stat-tracks").textContent = n(current.tracks.length);
  $("#period-label").textContent = periodName();
  renderRiver();
  renderArtists();
  renderTracks();
  renderRhythm();
  renderCalendar();
  const best = current.months.reduce(
    (a, b) => (amount(b) > amount(a) ? b : a),
    current.months[0],
  );
  if (best) {
    const leader = [...best.artists].sort(
      (a, b) => b[metric === "ms" ? 2 : 1] - a[metric === "ms" ? 2 : 1],
    )[0];
    $("#month-insight p").innerHTML =
      `<strong>${escapeHtml(fullMonth(best.month))}</strong> was the high-water mark: <strong>${units(amount(best))}</strong>${leader ? `, with <strong>${escapeHtml(data.artists[leader[0]])}</strong> leading the way` : ""}.`;
  }
}
function renderRiver() {
  const svg = d3.select("#river");
  svg.selectAll("*").remove();
  const narrow = innerWidth < 700,
    W = narrow ? 620 : 1200,
    H = 310,
    pad = 18;
  svg
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr(
      "aria-label",
      `Monthly ${metric === "ms" ? "listening time" : "plays"} for the top ten artists${includeOther ? " and all other artists" : ""}, ${periodName()}. Select an artist in the legend for its tracks.`,
    );
  const top = current.artists.slice(0, 10).map((a) => a.id),
    topSet = new Set(top),
    keys = [...top, ...(includeOther ? ["other"] : [])];
  const rows = current.months.map((m) => {
    const r = { month: m.month, total: amount(m) };
    keys.forEach((k) => (r[k] = 0));
    r.other = 0;
    for (const [id, p, t] of m.artists)
      r[topSet.has(id) ? id : "other"] += metric === "ms" ? t : p;
    return r;
  });
  const x = d3
    .scaleLinear()
    .domain([0, Math.max(rows.length - 1, 1)])
    .range([0, W]);
  const stack = d3
    .stack()
    .keys(keys)
    .offset(
      chartMode === "flow" ? d3.stackOffsetSilhouette : d3.stackOffsetNone,
    )(rows);
  const low = d3.min(stack, (s) => d3.min(s, (p) => p[0])) || 0,
    high = d3.max(stack, (s) => d3.max(s, (p) => p[1])) || 1;
  const y = d3
    .scaleLinear()
    .domain([low, high])
    .range([H - pad, pad]);
  const ticks = rows
    .map((r, i) => ({ r, i }))
    .filter(({ r, i }) =>
      selectedYear === "all" ? r.month.endsWith("-01") : i % 3 === 0,
    );
  const grid = svg.append("g").attr("class", "chart-grid");
  ticks.forEach(({ r, i }) => {
    grid
      .append("line")
      .attr("x1", x(i))
      .attr("x2", x(i))
      .attr("y1", 0)
      .attr("y2", H);
    grid
      .append("text")
      .attr("x", x(i) + 5)
      .attr("y", 12)
      .attr("fill", "#83916f")
      .attr("font-size", narrow ? 13 : 10)
      .text(
        selectedYear === "all"
          ? r.month.slice(0, 4)
          : fullMonth(r.month).split(" ")[0].slice(0, 3).toUpperCase(),
      );
  });
  const area = d3
    .area()
    .x((d, i) => x(i))
    .y0((d) => y(d[0]))
    .y1((d) => y(d[1]))
    .curve(d3.curveMonotoneX);
  const paths = svg
    .append("g")
    .selectAll("path")
    .data(stack)
    .join("path")
    .attr("d", area)
    .attr("fill", (d) => (d.key === "other" ? "#525e43" : color(d.key)))
    .attr("opacity", (d) =>
      selectedArtist === null || d.key === selectedArtist ? 1 : 0.2,
    )
    .attr("tabindex", (d) => (d.key === "other" ? -1 : 0))
    .attr("role", (d) => (d.key === "other" ? "img" : "button"))
    .attr(
      "aria-label",
      (d) =>
        `${d.key === "other" ? "All other artists" : data.artists[d.key]}. ${units(d3.sum(rows, (r) => r[d.key]))} in ${periodName()}.`,
    );
  function show(event, d) {
    let index;
    if (event.type === "focus") {
      index = d3.maxIndex(rows, (r) => r[d.key]);
      const b = event.target.getBoundingClientRect();
      event = { clientX: b.x + b.width / 2, clientY: b.y + b.height / 2 };
    } else {
      index = Math.max(
        0,
        Math.min(
          rows.length - 1,
          Math.round(x.invert(d3.pointer(event, svg.node())[0])),
        ),
      );
    }
    const r = rows[index];
    tooltip(
      event,
      `<small>${escapeHtml(fullMonth(r.month))}</small><strong>${escapeHtml(d.key === "other" ? "Other artists" : data.artists[d.key])}</strong>${units(r[d.key])} · ${r.total ? n((r[d.key] / r.total) * 100) : 0}% of the month`,
    );
    paths.attr("opacity", (p) => (p.key === d.key ? 1 : 0.22));
  }
  paths
    .on("pointermove", show)
    .on("focus", show)
    .on("pointerleave", () => {
      hideTooltip();
      paths.attr("opacity", (d) =>
        selectedArtist === null || d.key === selectedArtist ? 1 : 0.2,
      );
    })
    .on("blur", hideTooltip)
    .on("click", (event, d) => {
      if (d.key !== "other") selectArtist(d.key);
    })
    .on("keydown", (event, d) => {
      if ((event.key === "Enter" || event.key === " ") && d.key !== "other") {
        event.preventDefault();
        selectArtist(d.key);
      }
    });
  const start = rows[0]?.month,
    end = rows.at(-1)?.month;
  $(".chart-foot>span:first-child").textContent = start
    ? new Date(start + "-01T12:00Z")
        .toLocaleDateString("en-US", {
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        })
        .toUpperCase()
    : "";
  $("#end-label").textContent = end
    ? new Date(end + "-01T12:00Z")
        .toLocaleDateString("en-US", {
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        })
        .toUpperCase()
    : "";
  $("#legend").innerHTML =
    top
      .map(
        (id) =>
          `<button data-artist="${id}" class="${id === selectedArtist ? "selected" : ""}" aria-pressed="${id === selectedArtist}"><i class="swatch" style="--color:${color(id)}"></i>${escapeHtml(data.artists[id])}</button>`,
      )
      .join("") +
    `<button id="toggle-others" class="legend-other" aria-pressed="${includeOther}">${includeOther ? "− Hide" : "＋ Include"} other artists</button>`;
  $("#legend")
    .querySelectorAll("button[data-artist]")
    .forEach((b) => (b.onclick = () => selectArtist(Number(b.dataset.artist))));
  $("#toggle-others").onclick = () => {
    includeOther = !includeOther;
    renderRiver();
  };
  $("#flow-note").textContent = includeOther
    ? "The top 10 artists, plus everyone else."
    : "The top 10 artists, traced month by month.";
}
function selectArtist(id) {
  selectedArtist = selectedArtist === id ? null : id;
  trackLimit = 7;
  $("#track-search").value = "";
  renderRiver();
  renderArtists();
  renderTracks();
}
function renderArtists() {
  const artists = current.artists.slice(0, 10),
    max = amount(artists[0] || { ms: 1, plays: 1 });
  $("#artists").innerHTML = artists
    .map(
      (a, i) =>
        `<button class="artist-row ${a.id === selectedArtist ? "selected" : ""}" data-id="${a.id}" aria-pressed="${a.id === selectedArtist}"><span class="rank">${String(i + 1).padStart(2, "0")}</span><div><span class="artist-name"><i class="swatch" style="--color:${color(a.id)}"></i>${escapeHtml(data.artists[a.id])}</span><div class="artist-bar"><i style="--color:${color(a.id)};--width:${(amount(a) / max) * 100}%"></i></div></div><span class="artist-val">${units(amount(a), true)}</span></button>`,
    )
    .join("");
  $("#artists")
    .querySelectorAll("button")
    .forEach((b) => (b.onclick = () => selectArtist(Number(b.dataset.id))));
  $("#clear-artist").hidden = selectedArtist === null;
}
function renderTracks() {
  const query = $("#track-search").value.trim().toLowerCase();
  let rows = current.tracks.filter(
    (a) =>
      selectedArtist === null || data.tracks[a.id].artist === selectedArtist,
  );
  if (query)
    rows = rows.filter((a) => {
      const t = data.tracks[a.id];
      return `${t.title} ${data.artists[t.artist]} ${t.album}`
        .toLowerCase()
        .includes(query);
    });
  $("#tracks-heading").textContent =
    selectedArtist === null
      ? "Forever on repeat"
      : data.artists[selectedArtist];
  $("#tracks").innerHTML = rows.length
    ? rows
        .slice(0, trackLimit)
        .map((a, i) => {
          const t = data.tracks[a.id];
          return `<div class="track-row"><span class="rank">${String(i + 1).padStart(2, "0")}</span><div class="track-info"><a class="track-title" href="https://open.spotify.com/track/${encodeURIComponent(t.spotifyId)}" target="_blank" rel="noreferrer" title="${escapeHtml(t.title)} — open on Spotify">${escapeHtml(t.title)}</a><div class="track-artist">${escapeHtml(data.artists[t.artist])} <span aria-hidden="true">·</span> ${escapeHtml(t.album)}</div></div><div class="track-count">${metric === "ms" ? n(a.ms / 60000) : n(a.plays)}<small>${metric === "ms" ? "minutes" : "plays"}</small></div></div>`;
        })
        .join("")
    : '<p class="empty">No tracks match. Try another song or artist.</p>';
  $("#more-tracks").hidden = rows.length <= trackLimit;
}
function renderRhythm() {
  const hours = Array.from({ length: 24 }, () => [0, 0]),
    days = Array.from({ length: 7 }, () => [0, 0]);
  for (const r of data.rhythms.filter(
    (r) => selectedYear === "all" || String(r.year) === selectedYear,
  )) {
    r.hours.forEach((v, i) => {
      hours[i][0] += v[0];
      hours[i][1] += v[1];
    });
    r.weekdays.forEach((v, i) => {
      days[i][0] += v[0];
      days[i][1] += v[1];
    });
  }
  const idx = metric === "ms" ? 1 : 0,
    values = hours.map((h) => h[idx]),
    max = Math.max(...values, 1),
    peak = values.indexOf(Math.max(...values));
  const svg = d3.select("#clock");
  svg.selectAll("*").remove();
  svg.attr("viewBox", "0 0 320 320");
  const g = svg.append("g").attr("transform", "translate(160,160)");
  [78, 105, 133].forEach((r) =>
    g
      .append("circle")
      .attr("r", r)
      .attr("fill", "none")
      .attr("stroke", "#37472a")
      .attr("stroke-dasharray", "2 5"),
  );
  const arc = d3
    .arc()
    .innerRadius(70)
    .outerRadius((d) =>
      Math.sqrt(70 ** 2 + ((135 ** 2 - 70 ** 2) * values[d]) / max),
    )
    .startAngle((d) => (d / 24) * Math.PI * 2)
    .endAngle((d) => ((d + 1) / 24) * Math.PI * 2)
    .padAngle(0.028);
  g.selectAll("path")
    .data(d3.range(24))
    .join("path")
    .attr("d", arc)
    .attr("tabindex", 0)
    .attr("role", "img")
    .attr("aria-label", (d) => `${d}:00 UTC: ${units(values[d])}`)
    .on("focus", (e, d) => {
      const b = e.target.getBoundingClientRect();
      tooltip(
        { clientX: b.x, clientY: b.y },
        `<strong>${String(d).padStart(2, "0")}:00 UTC</strong>${units(values[d])}`,
      );
    })
    .on("blur", hideTooltip)
    .attr("fill", (d) => (d === peak ? "#e3f995" : "#78994d"))
    .attr("opacity", (d) => 0.55 + (0.45 * values[d]) / max)
    .on("pointermove", (e, d) =>
      tooltip(
        e,
        `<strong>${String(d).padStart(2, "0")}:00–${String((d + 1) % 24).padStart(2, "0")}:00 UTC</strong>${units(values[d])}`,
      ),
    )
    .on("pointerleave", hideTooltip)
    .append("title")
    .text((d) => `${d}:00 UTC: ${units(values[d])}`);
  [
    [0, "00"],
    [6, "06"],
    [12, "12"],
    [18, "18"],
  ].forEach(([h, label]) => {
    const a = (h / 24) * Math.PI * 2;
    g.append("text")
      .attr("x", Math.sin(a) * 151)
      .attr("y", -Math.cos(a) * 151 + 4)
      .attr("text-anchor", "middle")
      .text(label);
  });
  g.append("text")
    .attr("text-anchor", "middle")
    .attr("y", -6)
    .style("font-size", "33px")
    .style("fill", "#e9f3dc")
    .text(String(peak).padStart(2, "0") + ":00");
  g.append("text")
    .attr("text-anchor", "middle")
    .attr("y", 16)
    .style("font-size", "9px")
    .style("letter-spacing", "2px")
    .text("PEAK HOUR · UTC");
  $("#clock-caption").innerHTML =
    `The music peaks at <strong>${String(peak).padStart(2, "0")}:00 UTC</strong>. Each wedge adds up that hour across ${selectedYear === "all" ? "the whole archive" : selectedYear}.`;
  const dmax = Math.max(...days.map((d) => d[idx]), 1),
    total = days.reduce((s, d) => s + d[idx], 0),
    dp = days.findIndex((d) => d[idx] === dmax),
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  $(".weekdays-heading .muted").textContent =
    selectedYear === "all" ? "Whole archive" : selectedYear;
  $("#weekdays").innerHTML = days
    .map(
      (v, i) =>
        `<div class="weekday ${i === dp ? "peak" : ""}" title="${data.meta.weekdayOrder[i]}: ${units(v[idx])}, ${n((v[idx] / Math.max(total, 1)) * 100)}%"><i style="--height:${(v[idx] / dmax) * 62}px"></i><span>${labels[i]}</span></div>`,
    )
    .join("");
}
function renderCalendar() {
  const year = Number($("#calendar-year").value),
    source = data.days.filter((d) => d[0].startsWith(String(year))),
    map = new Map(source.map((d) => [d[0], d])),
    idx = metric === "ms" ? 2 : 1,
    max = Math.max(...source.map((d) => d[idx]), 1),
    svg = d3.select("#calendar");
  svg.selectAll("*").remove();
  const W = 730,
    H = 142,
    cell = 12.4,
    gap = 2.5,
    x0 = 31,
    y0 = 30,
    first = new Date(Date.UTC(year, 0, 1)),
    offset = first.getUTCDay(),
    end = new Date(Date.UTC(year + 1, 0, 1)),
    count = (end - first) / 86400000;
  svg
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr(
      "aria-label",
      `Daily listening calendar for ${year}, in UTC. Use arrow keys to move between dates`,
    );
  const scale = d3.scaleSqrt().domain([0, max]).range(["#304320", "#dff893"]);
  ["S", "M", "T", "W", "T", "F", "S"].forEach((d, i) =>
    svg
      .append("text")
      .attr("x", 5)
      .attr("y", y0 + i * cell + 8)
      .attr("font-size", 9)
      .attr("fill", "#8a9d71")
      .text(d),
  );
  for (let i = 0; i < 12; i++) {
    const day = new Date(Date.UTC(year, i, 1)),
      col = Math.floor(((day - first) / 86400000 + offset) / 7);
    svg
      .append("text")
      .attr("x", x0 + col * cell)
      .attr("y", 15)
      .attr("font-size", 10)
      .attr("fill", "#99ae7e")
      .text(
        day.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }),
      );
  }
  for (let i = 0; i < count; i++) {
    const date = new Date(+first + i * 86400000).toISOString().slice(0, 10),
      record = map.get(date),
      v = record?.[idx] || 0,
      within = date >= data.meta.period.start && date <= data.meta.period.end;
    svg
      .append("rect")
      .attr("x", x0 + Math.floor((i + offset) / 7) * cell)
      .attr("y", y0 + ((i + offset) % 7) * cell)
      .attr("width", cell - gap)
      .attr("height", cell - gap)
      .attr("rx", 1.5)
      .attr("fill", v ? scale(v) : within ? "#27351d" : "#181e13")
      .attr("stroke", within ? "none" : "#26301e")
      .attr("stroke-width", 0.5)
      .attr("tabindex", i === 0 ? 0 : -1)
      .attr("role", "img")
      .attr(
        "aria-label",
        `${date}: ${within ? units(v) : "outside export period"}`,
      )
      .on("focus", (e) => {
        const b = e.target.getBoundingClientRect();
        tooltip(
          { clientX: b.x, clientY: b.y },
          `<strong>${fullDate(date)}</strong>${within ? units(v) : "Outside the export period"}`,
        );
      })
      .on("blur", hideTooltip)
      .on("keydown", (e) => {
        const step = {
          ArrowRight: 7,
          ArrowLeft: -7,
          ArrowDown: 1,
          ArrowUp: -1,
        }[e.key];
        if (step) {
          e.preventDefault();
          const cells = svg.node().querySelectorAll("rect"),
            next = cells[Math.max(0, Math.min(count - 1, i + step))];
          e.target.setAttribute("tabindex", "-1");
          next.setAttribute("tabindex", "0");
          next.focus();
        }
      })
      .on("pointermove", (e) =>
        tooltip(
          e,
          `<strong>${fullDate(date)}</strong>${within ? units(v) : "Outside the export period"}`,
        ),
      )
      .on("pointerleave", hideTooltip)
      .append("title")
      .text(`${date}: ${within ? units(v) : "outside export period"}`);
  }
  const peak = source.reduce(
    (a, b) => (b[idx] > (a?.[idx] || 0) ? b : a),
    null,
  );
  $("#calendar-caption").innerHTML = peak
    ? `<strong>${n(source.length)} days</strong> with music in ${year}. The loudest square: <strong>${fullDate(peak[0])}</strong>, with ${units(peak[idx])}.`
    : "No qualifying listens in this year.";
}
function receiptData() {
  return [...current.tracks].sort((a, b) => b.plays - a.plays).slice(0, 10);
}
function openReceipt() {
  $("#receipt-period").textContent =
    selectedYear === "all"
      ? `${data.meta.period.start} / ${data.meta.period.end}`
      : `THE ${selectedYear} COLLECTION`;
  $("#receipt-tracks").innerHTML = receiptData()
    .map((a, i) => {
      const t = data.tracks[a.id];
      return `<li><span>${String(i + 1).padStart(2, "0")}</span><span>${escapeHtml(t.title)}<small>${escapeHtml(data.artists[t.artist])}</small></span><span>${n(a.plays)}</span></li>`;
    })
    .join("");
  $("#receipt-total").textContent = n(current.ms / 3600000) + " HOURS";
  $("#receipt-dialog").showModal();
}
function saveReceipt() {
  const rows = receiptData(),
    width = 480,
    cut = (s, l) => (s.length > l ? s.slice(0, l - 1) + "…" : s);
  let y = 175;
  let content = `<rect width="480" height="100%" fill="#f2f0df"/><g fill="#25271e" font-family="monospace"><text x="240" y="58" font-family="Arial,sans-serif" font-size="38" font-weight="900" text-anchor="middle">ON REPEAT</text><text x="240" y="95" font-size="18" text-anchor="middle">DEVIN’S LISTENING RECEIPT</text><text x="240" y="123" font-size="13" text-anchor="middle">${escapeHtml(selectedYear === "all" ? `${data.meta.period.start} / ${data.meta.period.end}` : `THE ${selectedYear} COLLECTION`)}</text><path d="M30 144H450" stroke="#777" stroke-dasharray="4 4"/><text x="30" y="165" font-size="12">QTY / TRACK</text><text x="450" y="165" text-anchor="end" font-size="12">PLAYS</text>`;
  rows.forEach((a, i) => {
    const t = data.tracks[a.id];
    y += 36;
    content += `<text x="30" y="${y}" font-size="13">${String(i + 1).padStart(2, "0")}</text><text x="62" y="${y}" font-size="13">${escapeHtml(cut(t.title, 41))}</text><text x="62" y="${y + 17}" font-size="11" opacity=".65">${escapeHtml(cut(data.artists[t.artist], 42))}</text><text x="450" y="${y}" font-size="13" text-anchor="end">${n(a.plays)}</text>`;
    y += 20;
  });
  y += 32;
  content += `<path d="M30 ${y}H450" stroke="#777" stroke-dasharray="4 4"/><text x="30" y="${y + 30}" font-size="14">TOTAL LISTENING</text><text x="450" y="${y + 30}" font-size="14" text-anchor="end">${n(current.ms / 3600000)} HOURS</text><text x="240" y="${y + 80}" font-size="13" text-anchor="middle">THANK YOU FOR THE MUSIC.</text><text x="240" y="${y + 102}" font-size="13" text-anchor="middle">KEEP LISTENING.</text></g>`;
  const height = y + 140,
    svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${content}</svg>`,
    url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" })),
    link = document.createElement("a");
  link.href = url;
  link.download = `devin-on-repeat-${selectedYear}.svg`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function init() {
  try {
    const res = await fetch("data/history.json");
    if (!res.ok) throw new Error("Unable to load listening data");
    data = await res.json();
    data.colorOrder = new Map(
      aggregate(data.months).artists.map((a, i) => [a.id, i]),
    );
    $("#date-range").textContent =
      `${data.meta.years[0]}—${data.meta.years.at(-1)}`;
    $("#archive-count").textContent =
      `${n(data.meta.qualifiedEvents)} listens. ${data.meta.years.length} calendar years.`;
    $("#years").innerHTML = ["all", ...data.meta.years]
      .map(
        (y) =>
          `<button data-year="${y}" aria-pressed="${y === "all"}">${y === "all" ? "All time" : y}</button>`,
      )
      .join("");
    $("#years")
      .querySelectorAll("button")
      .forEach((b) => (b.onclick = () => setYear(b.dataset.year)));
    $("#calendar-year").innerHTML = data.meta.years
      .map((y) => `<option value="${y}">${y}</option>`)
      .join("");
    $("#calendar-year").value = data.meta.years.at(-1);
    $("#calendar-year").onchange = renderCalendar;
    document.querySelectorAll("[data-metric]").forEach(
      (b) =>
        (b.onclick = () => {
          metric = b.dataset.metric;
          render();
        }),
    );
    document.querySelectorAll("[data-mode]").forEach(
      (b) =>
        (b.onclick = () => {
          chartMode = b.dataset.mode;
          document.querySelectorAll("[data-mode]").forEach((a) => {
            a.classList.toggle("active", a === b);
            a.setAttribute("aria-pressed", String(a === b));
          });
          renderRiver();
        }),
    );
    $("#clear-artist").onclick = () => selectArtist(selectedArtist);
    $("#track-search").oninput = () => {
      trackLimit = 7;
      renderTracks();
    };
    $("#more-tracks").onclick = () => {
      trackLimit += 10;
      renderTracks();
    };
    $("#receipt-open").onclick = openReceipt;
    $("#receipt-open-bottom").onclick = openReceipt;
    $("#receipt-close").onclick = () => $("#receipt-dialog").close();
    $("#receipt-save").onclick = saveReceipt;
    $("#receipt-dialog").addEventListener("click", (e) => {
      if (e.target === $("#receipt-dialog")) {
        const r = e.target.getBoundingClientRect();
        if (
          e.clientX < r.left ||
          e.clientX > r.right ||
          e.clientY < r.top ||
          e.clientY > r.bottom
        )
          e.target.close();
      }
    });
    $("#loading").hidden = true;
    $("#app").hidden = false;
    render();
    let resizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(renderRiver, 150);
    });
    window.addEventListener("scroll", hideTooltip, { passive: true });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") hideTooltip();
    });
  } catch (e) {
    $("#loading").hidden = false;
    $("#app").hidden = true;
    $("#loading").textContent =
      "The archive couldn’t load. Please refresh to try again.";
    console.error(e);
  }
}
init();
