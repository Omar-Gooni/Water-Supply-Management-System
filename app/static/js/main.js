// ================== WSMS Sidebar Toggle (FULL with overlay + logs) ==================
document.addEventListener('DOMContentLoaded', function () {
  console.log('[WSMS] DOMContentLoaded fired');

  const btn = document.getElementById('menuToggle');
  if (!btn) {
    console.warn('[WSMS] menuToggle button NOT found. Ensure header is included and the element has id="menuToggle".');
    return;
  }
  console.log('[WSMS] menuToggle button found:', btn);

  // Create overlay if not present
  let overlay = document.getElementById('sidebarOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'sidebarOverlay';
    document.body.appendChild(overlay);
    console.log('[WSMS] Created overlay element');
  }

  const isMobile = () => window.matchMedia('(max-width: 992px)').matches;

  const applyDesktopStateFromStorage = () => {
    const savedRaw = localStorage.getItem('wsms.sidebarCollapsed');
    const savedCollapsed = savedRaw === 'true';
    console.log('[WSMS] Restoring desktop state from localStorage:', savedRaw);

    if (savedCollapsed) {
      document.body.classList.add('is-collapsed');
    } else {
      document.body.classList.remove('is-collapsed');
    }
    document.body.classList.remove('overlay-active'); // no overlay on desktop by default
  };

  const applyMobileDefaultCollapsed = () => {
    document.body.classList.add('is-collapsed');      // default collapsed
    document.body.classList.remove('overlay-active'); // overlay hidden initially
    console.log('[WSMS] Applied mobile default: collapsed');
  };

  // Init: set correct state based on screen size
  const initState = () => {
    if (isMobile()) {
      applyMobileDefaultCollapsed();
    } else {
      applyDesktopStateFromStorage();
    }
    syncAria();
  };

  // Update ARIA
  const syncAria = () => {
    const expanded = !document.body.classList.contains('is-collapsed');
    btn.setAttribute('aria-controls', 'sidebar');
    btn.setAttribute('role', 'button');
    btn.setAttribute('tabindex', '0');
    btn.setAttribute('aria-expanded', String(expanded));
    console.log('[WSMS] aria-expanded =', expanded);
  };

  // Toggle behavior
  const toggle = () => {
    const before = document.body.classList.contains('is-collapsed');
    document.body.classList.toggle('is-collapsed');
    const after = document.body.classList.contains('is-collapsed');
    console.log(`[WSMS] Toggle clicked. wasCollapsed=${before} -> nowCollapsed=${after}`);

    if (isMobile()) {
      // Show overlay only when sidebar is open on mobile
      if (!after) {
        document.body.classList.add('overlay-active');
      } else {
        document.body.classList.remove('overlay-active');
      }
    } else {
      // Save state on desktop only
      localStorage.setItem('wsms.sidebarCollapsed', String(after));
    }
    syncAria();
  };

  // Close when clicking overlay (mobile)
  overlay.addEventListener('click', () => {
    if (isMobile() && !document.body.classList.contains('is-collapsed')) {
      console.log('[WSMS] Overlay clicked → collapsing sidebar');
      document.body.classList.add('is-collapsed');
      document.body.classList.remove('overlay-active');
      syncAria();
    }
  });

  // Bind events
  btn.addEventListener('click', toggle);
  btn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      console.log('[WSMS] Keydown on toggle:', e.key);
      toggle();
    }
  });

  // Handle resize: switch behaviors between mobile/desktop smoothly
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const mobile = isMobile();
      console.log('[WSMS] Resize detected. isMobile =', mobile);
      if (mobile) {
        applyMobileDefaultCollapsed();
      } else {
        applyDesktopStateFromStorage();
      }
      syncAria();
    }, 120);
  });

  // Expose a helper to debug from console
  window.__wsmsToggle = toggle;

  // Initialize state
  initState();
  console.log('[WSMS] Toggle ready. Try: window.__wsmsToggle() in console');
});


// ================== Sidebar Submenu Toggle ==================
document.addEventListener("DOMContentLoaded", function() {
  
  // Find all sidebar submenu toggles
  const toggles = document.querySelectorAll(".sidebar .js-submenu-toggle");

  toggles.forEach(toggle => {
    toggle.addEventListener("click", function(event) {
      
      // Stop the link from navigating (since href="#")
      event.preventDefault(); 
      
      // Get the submenu, which is the *next element*
      const submenu = this.nextElementSibling;

      if (submenu && submenu.classList.contains("submenu")) {
        
        // Check if the submenu is already open
        const isOpen = submenu.classList.contains("open");
        
        if (isOpen) {
          // --- Close it ---
          submenu.classList.remove("open");
          this.classList.remove("open"); // For the arrow
          submenu.style.maxHeight = "0";
        } else {
          // --- Open it ---
          submenu.classList.add("open");
          this.classList.add("open"); // For the arrow
          
          // Set max-height to the content's full height
          submenu.style.maxHeight = submenu.scrollHeight + "px";
        }
      }
    });
  });

});
