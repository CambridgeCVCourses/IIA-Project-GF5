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
      const photoStack = carousel.querySelector("[data-photo-stack]");
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

      let dragStartX = 0;
      let dragStartY = 0;
      let dragPointerId = null;
      let didDrag = false;
      let suppressClick = false;

      function canSwipePhotos() {
        return window.matchMedia("(max-width: 700px)").matches;
      }

      function endDrag(event) {
        if (dragPointerId === null || event.pointerId !== dragPointerId) {
          return;
        }

        const deltaX = event.clientX - dragStartX;
        const deltaY = event.clientY - dragStartY;
        dragPointerId = null;
        if (!didDrag || Math.abs(deltaX) < 42 || Math.abs(deltaX) < Math.abs(deltaY) * 1.4) {
          didDrag = false;
          restartTimer();
          return;
        }

        suppressClick = true;
        didDrag = false;
        setActive(activeIndex + (deltaX < 0 ? 1 : -1));
        restartTimer();
        window.setTimeout(() => {
          suppressClick = false;
        }, 0);
      }

      slides.forEach((slide) => {
        function activateSlide() {
          if (suppressClick) {
            suppressClick = false;
            return;
          }

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

      if (photoStack) {
        photoStack.addEventListener("pointerdown", (event) => {
          if (event.pointerType === "mouse" || !canSwipePhotos()) {
            return;
          }

          dragPointerId = event.pointerId;
          dragStartX = event.clientX;
          dragStartY = event.clientY;
          didDrag = false;
          window.clearInterval(timer);
        });

        photoStack.addEventListener("pointermove", (event) => {
          if (dragPointerId === null || event.pointerId !== dragPointerId) {
            return;
          }

          const deltaX = event.clientX - dragStartX;
          const deltaY = event.clientY - dragStartY;
          if (Math.abs(deltaX) > 12 && Math.abs(deltaX) > Math.abs(deltaY)) {
            didDrag = true;
          }
        });

        photoStack.addEventListener("pointerup", endDrag);
        photoStack.addEventListener("pointercancel", endDrag);
      }

      carousel.addEventListener("pointerenter", () => window.clearInterval(timer));
      carousel.addEventListener("pointerleave", () => {
        if (dragPointerId === null) {
          restartTimer();
        }
      });
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
      const thumbnailRail = showcase.querySelector("[data-thumbnail-rail]");
      const thumbnailStrip = showcase.querySelector("[data-thumbnail-strip]");
      const scrollButtons = Array.from(showcase.querySelectorAll("[data-thumbnail-scroll]"));
      if (!player || !source || !caption || !thumbs.length) {
        return;
      }

      function updateThumbnailScrollState() {
        if (!thumbnailRail || !thumbnailStrip) {
          return;
        }

        const hasOverflow = thumbnailStrip.scrollWidth > thumbnailStrip.clientWidth + 1;
        const isAtStart = thumbnailStrip.scrollLeft <= 1;
        const isAtEnd =
          thumbnailStrip.scrollLeft + thumbnailStrip.clientWidth >= thumbnailStrip.scrollWidth - 1;
        thumbnailRail.classList.toggle("has-overflow", hasOverflow);
        thumbnailRail.classList.toggle("is-at-start", !hasOverflow || isAtStart);
        thumbnailRail.classList.toggle("is-at-end", !hasOverflow || isAtEnd);
      }

      function setVideo(button, shouldPlay) {
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
        if (shouldPlay) {
          const playPromise = player.play();
          if (playPromise && typeof playPromise.catch === "function") {
            playPromise.catch(() => {});
          }
        }

        thumbs.forEach((thumb) => {
          const isActive = thumb === button;
          thumb.classList.toggle("is-active", isActive);
          thumb.setAttribute("aria-current", isActive ? "true" : "false");
        });

        button.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }

      thumbs.forEach((button) => {
        button.addEventListener("click", () => setVideo(button, true));
      });

      if (thumbnailRail && thumbnailStrip) {
        scrollButtons.forEach((button) => {
          button.addEventListener("click", () => {
            const direction = button.getAttribute("data-thumbnail-scroll") === "left" ? -1 : 1;
            thumbnailStrip.scrollBy({
              left: direction * thumbnailStrip.clientWidth * 0.75,
              behavior: "smooth",
            });
          });
        });

        thumbnailStrip.addEventListener("scroll", updateThumbnailScrollState, { passive: true });
        window.addEventListener("resize", updateThumbnailScrollState);
        if ("ResizeObserver" in window) {
          new ResizeObserver(updateThumbnailScrollState).observe(thumbnailStrip);
        }
        requestAnimationFrame(updateThumbnailScrollState);
      }
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
