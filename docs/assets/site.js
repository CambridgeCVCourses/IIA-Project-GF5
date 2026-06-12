(function () {
  function getTrigger(dropdown) {
    return dropdown.querySelector("[data-nav-dropdown-trigger]");
  }

  function closeDropdown(dropdown) {
    const trigger = getTrigger(dropdown);
    dropdown.classList.remove("is-open");
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
    if (dropdown.contains(document.activeElement) && document.activeElement) {
      document.activeElement.blur();
    }
  }

  function openDropdown(dropdown) {
    const trigger = getTrigger(dropdown);
    dropdown.classList.add("is-open");
    if (trigger) {
      trigger.setAttribute("aria-expanded", "true");
    }
  }

  function initDropdowns() {
    const dropdowns = Array.from(document.querySelectorAll("[data-nav-dropdown]"));
    if (!dropdowns.length) {
      return;
    }

    function closeAll(except) {
      dropdowns.forEach((dropdown) => {
        if (dropdown !== except) {
          closeDropdown(dropdown);
        }
      });
    }

    dropdowns.forEach((dropdown) => {
      const trigger = getTrigger(dropdown);
      if (!trigger) {
        return;
      }

      dropdown.addEventListener("pointerenter", (event) => {
        if (event.pointerType === "touch") {
          return;
        }
        closeAll(dropdown);
        openDropdown(dropdown);
      });

      dropdown.addEventListener("pointerleave", (event) => {
        if (event.pointerType === "touch") {
          return;
        }
        closeDropdown(dropdown);
      });

      trigger.addEventListener("click", (event) => {
        event.preventDefault();
        const nextOpen = !dropdown.classList.contains("is-open");
        closeAll(dropdown);
        dropdown.classList.toggle("is-open", nextOpen);
        trigger.setAttribute("aria-expanded", nextOpen ? "true" : "false");
        if (!nextOpen) {
          trigger.blur();
        }
      });
    });

    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) {
        closeAll();
        return;
      }
      if (!event.target.closest("[data-nav-dropdown]")) {
        closeAll();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAll();
      }
    });
  }

  function initPresentationOrderTools() {
    const tools = Array.from(document.querySelectorAll("[data-presentation-order]"));
    if (!tools.length) {
      return;
    }

    function namesFromResult(result) {
      return Array.from(result.querySelectorAll("li"))
        .map((item) => {
          const label = item.querySelector("span");
          return (label ? label.textContent : item.textContent || "").trim();
        })
        .filter(Boolean);
    }

    function assignmentsFromResult(result) {
      const assignments = new Map();
      result.querySelectorAll("li").forEach((item) => {
        const label = item.querySelector("span");
        const input = item.querySelector("[data-order-assignment]");
        const name = (label ? label.textContent : item.textContent || "").trim();
        if (name && input) {
          assignments.set(name, input.value);
        }
      });
      return assignments;
    }

    function randomIndex(maxExclusive) {
      if (window.crypto && window.crypto.getRandomValues) {
        const values = new Uint32Array(1);
        window.crypto.getRandomValues(values);
        return values[0] % maxExclusive;
      }
      return Math.floor(Math.random() * maxExclusive);
    }

    function shuffled(values) {
      const next = values.slice();
      for (let index = next.length - 1; index > 0; index -= 1) {
        const swapIndex = randomIndex(index + 1);
        [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
      }
      return next;
    }

    function render(result, order, assignments) {
      result.innerHTML = "";
      order.forEach((name) => {
        const item = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = name;
        const input = document.createElement("input");
        input.type = "text";
        input.inputMode = "numeric";
        input.placeholder = "No.";
        input.setAttribute("aria-label", "Group order");
        input.setAttribute("data-order-assignment", "");
        input.value = assignments && assignments.has(name) ? assignments.get(name) : "";
        item.append(label, input);
        result.appendChild(item);
      });
    }

    tools.forEach((tool) => {
      const result = tool.querySelector("[data-order-result]");
      const shuffleButton = tool.querySelector("[data-order-shuffle]");
      if (!result || !shuffleButton) {
        return;
      }

      let currentOrder = namesFromResult(result);
      shuffleButton.addEventListener("click", () => {
        const assignments = assignmentsFromResult(result);
        currentOrder = shuffled(currentOrder.length ? currentOrder : namesFromResult(result));
        render(result, currentOrder, assignments);
      });
    });
  }

  function initPhotoCarousels() {
    const carousels = Array.from(document.querySelectorAll("[data-photo-carousel]"));
    carousels.forEach((carousel) => {
      const slides = Array.from(carousel.querySelectorAll("[data-photo-slide]"));
      if (slides.length < 2) {
        return;
      }

      let activeIndex = slides.findIndex((slide) => slide.classList.contains("is-active"));
      if (activeIndex < 0) {
        activeIndex = 0;
      }

      function setActive(index) {
        activeIndex = (index + slides.length) % slides.length;
        slides.forEach((slide, slideIndex) => {
          const isActive = slideIndex === activeIndex;
          slide.classList.toggle("is-active", isActive);
          slide.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
      }

      let timer = window.setInterval(() => setActive(activeIndex + 1), 4500);

      function restartTimer() {
        window.clearInterval(timer);
        timer = window.setInterval(() => setActive(activeIndex + 1), 4500);
      }

      slides.forEach((slide) => {
        function activateSlide() {
          const index = Number.parseInt(slide.getAttribute("data-photo-index") || "0", 10);
          if (index !== activeIndex) {
            setActive(index);
            restartTimer();
          }
        }

        slide.addEventListener("click", activateSlide);
        slide.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activateSlide();
          }
        });
      });

      carousel.addEventListener("pointerenter", () => window.clearInterval(timer));
      carousel.addEventListener("pointerleave", restartTimer);
      carousel.addEventListener("focusin", () => window.clearInterval(timer));
      carousel.addEventListener("focusout", restartTimer);
    });
  }

  function initAnimationShowcases() {
    const showcases = Array.from(document.querySelectorAll("[data-animation-showcase]"));
    showcases.forEach((showcase) => {
      const player = showcase.querySelector("[data-animation-player]");
      const source = showcase.querySelector("[data-animation-source]");
      const caption = showcase.querySelector("[data-animation-caption]");
      const thumbs = Array.from(showcase.querySelectorAll("[data-video-src]"));
      if (!player || !source || !caption || !thumbs.length) {
        return;
      }

      function setVideo(button) {
        const videoSrc = button.getAttribute("data-video-src");
        const poster = button.getAttribute("data-video-poster");
        const nextCaption = button.getAttribute("data-video-caption") || "";
        if (!videoSrc) {
          return;
        }

        player.pause();
        source.setAttribute("src", videoSrc);
        if (poster) {
          player.setAttribute("poster", poster);
        }
        caption.textContent = nextCaption;
        player.load();

        thumbs.forEach((thumb) => {
          const isActive = thumb === button;
          thumb.classList.toggle("is-active", isActive);
          thumb.setAttribute("aria-current", isActive ? "true" : "false");
        });
      }

      thumbs.forEach((button) => {
        button.addEventListener("click", () => setVideo(button));
      });
    });
  }

  function init() {
    initDropdowns();
    initPresentationOrderTools();
    initPhotoCarousels();
    initAnimationShowcases();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
