/**
 * Dashboard client — connects to Socket.IO /seats namespace
 * and renders a live seat grid.
 */
(function () {
    "use strict";

    const grid = document.getElementById("seat-grid");
    const seatData = {}; // seat_id → latest state object

    // ── Socket.IO connection ───────────────────────────────────
    const socket = io("/seats", {
        transports: ["websocket", "polling"],
    });

    socket.on("connect", () => {
        console.log("[Socket.IO] connected");
        // Also fetch full state via REST on connect
        fetch("/api/seats")
            .then((r) => r.json())
            .then((seats) => seats.forEach(handleUpdate));
    });

    socket.on("seat_update", handleUpdate);

    socket.on("disconnect", () => console.log("[Socket.IO] disconnected"));

    // ── State helpers ──────────────────────────────────────────

    const STATE_LABELS = {
        vacant: "Vacant",
        occupied: "Occupied",
        reserved: "Reserved",
        suspected_hoarding: "Suspected Hoarding",
        confirmed_hoarding: "Confirmed Hoarding",
        ghost_occupied: "Ghost Occupied",
    };

    function handleUpdate(data) {
        seatData[data.seat_id] = data;
        renderSeat(data);
        updateStats();
    }

    // ── Rendering ──────────────────────────────────────────────

    function renderSeat(data) {
        let card = document.getElementById("seat-" + data.seat_id);
        if (!card) {
            card = document.createElement("div");
            card.id = "seat-" + data.seat_id;
            card.className = "seat-card";
            card.innerHTML = `
                <span class="seat-id"></span>
                <span class="seat-state"></span>
                <span class="seat-student"></span>
                <span class="seat-time"></span>
                <button class="btn-reset">Staff Reset</button>
            `;
            card.querySelector(".btn-reset").addEventListener("click", () => {
                staffReset(data.seat_id);
            });
            grid.appendChild(card);
        }

        // Update classes
        card.className = "seat-card " + data.state;

        // Update text
        card.querySelector(".seat-id").textContent = data.seat_id;
        card.querySelector(".seat-state").textContent =
            STATE_LABELS[data.state] || data.state;
        card.querySelector(".seat-student").textContent = data.student_id
            ? "Student: " + data.student_id
            : "";

        // Time info
        let timeText = "";
        if (data.reservation_remaining_s != null) {
            timeText = "⏱ " + Math.round(data.reservation_remaining_s) + "s remaining";
        } else if (data.timestamp) {
            const d = new Date(data.timestamp * 1000);
            timeText = "Updated " + d.toLocaleTimeString();
        }
        card.querySelector(".seat-time").textContent = timeText;
    }

    function updateStats() {
        const all = Object.values(seatData);
        const count = (state) => all.filter((s) => s.state === state).length;

        document.querySelector("#stat-total").textContent =
            "Total: " + all.length;
        document.querySelector(".stat.vacant").textContent =
            "Vacant: " + count("vacant");
        document.querySelector(".stat.occupied").textContent =
            "Occupied: " + count("occupied");
        document.querySelector(".stat.reserved").textContent =
            "Reserved: " +
            (count("reserved"));
        document.querySelector(".stat.hoarded").textContent =
            "Hoarded: " +
            (count("suspected_hoarding") + count("confirmed_hoarding") + count("ghost_occupied"));
    }

    // ── Actions ────────────────────────────────────────────────

    function staffReset(seatId) {
        fetch("/api/staff-reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ seat_id: seatId }),
        })
            .then((r) => r.json())
            .then((data) => console.log("[Reset]", data));
    }
})();
