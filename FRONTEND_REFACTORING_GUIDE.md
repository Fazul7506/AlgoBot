# Frontend Audit Checklist & Refactoring Guide

**Status**: ⚠️ NEEDS PROFESSIONAL REFACTORING  
**Priority**: P2 (Medium) - Critical for UX but not for trading integrity  
**Estimated Effort**: 40-60 hours

---

## FRONTEND STRUCTURE OVERVIEW

```
static/
  ├── css/          # Needs modularization
  ├── js/           # Needs modularization  
  ├── charts/       # Chart libraries
  ├── plugins/      # Third-party plugins
  └── vendors/      # Vendor files

templates/
  ├── base.html     # Main layout
  ├── accounts/     # Account management
  ├── broker/       # Broker connections
  ├── dashboard/    # Dashboard pages
  ├── trading/      # Trading interface
  └── ... (30+ app-specific templates)
```

---

## CRITICAL AUDIT CHECKLIST

### HTML QUALITY

#### Semantic HTML
- [ ] Use `<header>`, `<nav>`, `<main>`, `<article>`, `<aside>`, `<footer>`
- [ ] Use `<section>` and `<article>` appropriately
- [ ] Use `<form>` for all forms, not divs with inputs
- [ ] Use proper heading hierarchy (h1-h6, no skipping levels)
- [ ] Use `<table>` for tabular data, not layout
- [ ] Use `<ul>`, `<ol>`, `<dl>` for lists, not nested divs

#### Accessibility
- [ ] All form inputs have associated `<label>` tags
- [ ] Images have descriptive `alt` attributes
- [ ] Links have meaningful text (not "click here")
- [ ] Color is never used alone to convey information
- [ ] Focus states are visible for all interactive elements
- [ ] ARIA labels/roles used where HTML semantics insufficient
- [ ] Page has proper `<title>` and meta tags
- [ ] Keyboard navigation works throughout
- [ ] Tab order is logical
- [ ] Skip links present for navigation

#### Validation
- [ ] No inline styles (all CSS in stylesheets)
- [ ] No inline JavaScript event handlers (use event listeners)
- [ ] Proper HTML5 doctype
- [ ] Closing tags for all elements
- [ ] No deprecated attributes
- [ ] Proper encoding specified

### CSS QUALITY

#### Organization
- [ ] CSS organized into logical modules (base, components, layouts, pages)
- [ ] No more than 5-10 CSS files (combine related styles)
- [ ] Consistent naming convention (BEM, SMACSS, or similar)
- [ ] Related properties grouped together
- [ ] Clear separation of concerns

#### Maintainability
- [ ] CSS variables for colors, spacing, typography
- [ ] Consistent spacing scale (4px, 8px, 16px, 32px units)
- [ ] Consistent color palette (defined once, reused everywhere)
- [ ] Typography scale (h1-h6, body, small text)
- [ ] No magic numbers or hardcoded values
- [ ] DRY principle applied (no duplication)
- [ ] Minimal use of `!important` (only for overrides)

#### Responsive Design
- [ ] Mobile-first approach
- [ ] Breakpoints clearly defined (320px, 768px, 1024px, 1280px)
- [ ] Flexbox/Grid for layouts (no float-based layouts)
- [ ] Images and media responsive
- [ ] Touch-friendly targets (minimum 44x44px)
- [ ] Viewport meta tag present

#### States & Interactions
- [ ] Hover states for all interactive elements
- [ ] Focus states for keyboard navigation
- [ ] Active/current page states
- [ ] Loading states
- [ ] Error states
- [ ] Disabled states
- [ ] Smooth transitions/animations (respects prefers-reduced-motion)

#### Performance
- [ ] Minimal CSS bundle size
- [ ] No unused CSS (unused styles removed)
- [ ] Critical CSS inlined or prioritized
- [ ] Efficient selectors (avoid deep nesting)
- [ ] No CSS-in-JS that could be CSS files

### JAVASCRIPT QUALITY

#### Architecture
- [ ] Code organized into modules (api, services, components, utils)
- [ ] Clear separation of concerns
- [ ] No global variables (all in namespaces/modules)
- [ ] Async/await for promises (not .then() chains)
- [ ] Error handling with try/catch blocks
- [ ] Logging structured with identifiers (request_id, user_id, etc.)

#### API Integration
- [ ] Consistent API client module
- [ ] Request/response interceptors
- [ ] Error handling for all API calls
- [ ] Loading states before requests
- [ ] Proper status code handling
- [ ] Timeout handling
- [ ] Retry logic with exponential backoff
- [ ] No hardcoded API URLs
- [ ] Proper headers (authentication, content-type)
- [ ] CSRF token handling

#### DOM Manipulation
- [ ] No innerHTML with user content (XSS prevention)
- [ ] Proper escaping/sanitization
- [ ] Event delegation where appropriate
- [ ] Proper cleanup/memory management
- [ ] No global selectors (prefix with context)
- [ ] Efficient DOM queries (cache selectors)

#### State Management
- [ ] Single source of truth for critical state
- [ ] No state duplication between DOM and JS
- [ ] Proper data flow (unidirectional if possible)
- [ ] WebSocket state synchronized with server
- [ ] Optimistic updates only for safe operations

#### WebSocket Integration
- [ ] Real-time connection status indicator
- [ ] Reconnection with exponential backoff
- [ ] Heartbeat/ping mechanism
- [ ] Message validation
- [ ] Proper subscription/unsubscription
- [ ] Graceful degradation if WebSocket unavailable

#### Testing
- [ ] Unit tests for utilities
- [ ] Integration tests for API interactions
- [ ] No hardcoded test data in production
- [ ] Test coverage > 60%

#### Performance
- [ ] Minified and bundled for production
- [ ] Code splitting by feature/page
- [ ] Lazy loading for heavy components
- [ ] Debouncing for high-frequency events
- [ ] Caching where appropriate
- [ ] No blocking operations

#### Security
- [ ] No credentials in JavaScript
- [ ] CSRF tokens on form submissions
- [ ] Content Security Policy headers
- [ ] No eval() or dynamic code execution
- [ ] Proper CORS configuration
- [ ] Input validation before sending to API

---

## SPECIFIC FILE AUDIT RESULTS

### Static CSS Files to Review
```
static/css/
├── base.css              # Foundation styles (AUDIT)
├── components.css        # Component styles (AUDIT)
├── dashboard.css         # Dashboard specific (AUDIT)
├── trading.css          # Trading interface (AUDIT)
├── responsive.css       # Media queries (AUDIT)
└── ... (additional files)
```

**Audit Results**:
- [ ] No inline `<style>` tags found in templates
- [ ] No `style=""` attributes in HTML
- [ ] All CSS in proper files
- [ ] Organized by component/page
- [ ] Responsive breakpoints defined

### Static JS Files to Review
```
static/js/
├── core/
│   ├── api.js            # API client module
│   ├── broker_state.js   # Broker connection state
│   ├── websocket.js      # WebSocket manager
│   └── auth.js           # Authentication
├── components/
│   ├── broker_accounts.js
│   ├── trading_terminal.js
│   └── dashboard.js
├── pages/
│   └── ... (page-specific)
└── utils/
    └── ... (utilities)
```

**Key Files to Review**:
1. `api.js` - Verify error handling and request/response logic
2. `websocket.js` - Verify reconnection and state management
3. `broker_state.js` - Verify real-time updates
4. `trading_terminal.js` - Verify pre-trade checks
5. `dashboard.js` - Verify data freshness

### Template Files to Review
**Critical Templates**:
1. `base.html` - Main layout (check semantics)
2. `broker/broker_accounts.html` - Broker connection UI
3. `dashboard/dashboard.html` - Main dashboard
4. `trading/trading.html` - Trading interface
5. `accounts/profile.html` - User profile

---

## REFACTORING ROADMAP

### Phase 1: CSS Refactoring (10-15 hours)

#### Step 1.1: Create CSS Architecture
```css
/* static/css/01-base.css */
/* Foundation: variables, reset, typography */
:root {
  --color-primary: #2563eb;
  --color-success: #16a34a;
  --color-warning: #ca8a04;
  --color-error: #dc2626;
  --color-text: #1f2937;
  --color-bg: #ffffff;
  
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 32px;
  --spacing-xl: 64px;
  
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto;
  --font-size-sm: 12px;
  --font-size-md: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 20px;
}

/* Reset and base elements */
* { margin: 0; padding: 0; box-sizing: border-box; }
html { font-size: 16px; }
body { font-family: var(--font-sans); color: var(--color-text); }
```

#### Step 1.2: Component Styles
```css
/* static/css/02-components.css */
/* Buttons, forms, cards, etc. */

.btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.btn--primary {
  background: var(--color-primary);
  color: white;
}

.btn--primary:hover {
  background: #1d4ed8;
}

/* Focus state for accessibility */
.btn:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

#### Step 1.3: Layout Styles
```css
/* static/css/03-layouts.css */
.layout-main {
  display: flex;
  min-height: 100vh;
}

.layout-sidebar {
  width: 250px;
  background: #f3f4f6;
  overflow-y: auto;
}

.layout-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

/* Responsive */
@media (max-width: 768px) {
  .layout-main { flex-direction: column; }
  .layout-sidebar { width: 100%; }
}
```

#### Step 1.4: Dark Mode Support
```css
@media (prefers-color-scheme: dark) {
  :root {
    --color-text: #f3f4f6;
    --color-bg: #1f2937;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

### Phase 2: HTML Refactoring (15-20 hours)

#### Step 2.1: Template Semantic Cleanup
**Before**:
```html
<div id="main-container">
  <div id="header"> <!-- header content --> </div>
  <div id="content"> <!-- page content --> </div>
</div>
```

**After**:
```html
<main>
  <header role="banner">
    <!-- header content -->
  </header>
  <article>
    <!-- page content -->
  </article>
</main>
```

#### Step 2.2: Form Accessibility
**Before**:
```html
<div>
  <input type="email" placeholder="Email">
</div>
```

**After**:
```html
<div class="form-group">
  <label for="email">Email Address</label>
  <input type="email" id="email" name="email" required aria-describedby="email-help">
  <small id="email-help">We'll never share your email.</small>
</div>
```

#### Step 2.3: Navigation Structure
**Before**:
```html
<div class="nav">
  <a href="/">Home</a>
  <a href="/dashboard">Dashboard</a>
</div>
```

**After**:
```html
<nav aria-label="Main Navigation">
  <ul>
    <li><a href="/" aria-current="page">Home</a></li>
    <li><a href="/dashboard">Dashboard</a></li>
  </ul>
</nav>
```

### Phase 3: JavaScript Refactoring (25-30 hours)

#### Step 3.1: Create API Module
```javascript
// static/js/core/api.js
export class APIClient {
  constructor(baseURL = '/api') {
    this.baseURL = baseURL;
    this.requestID = null;
  }
  
  async request(method, path, data = null) {
    const url = `${this.baseURL}${path}`;
    const options = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': crypto.randomUUID(),
        'X-CSRF-Token': this._getCsrfToken(),
      },
    };
    
    if (data) options.body = JSON.stringify(data);
    
    try {
      const response = await fetch(url, options);
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new APIError(error.detail || 'API request failed', response.status);
      }
      
      return await response.json();
    } catch (error) {
      console.error('API error:', { path, method, error });
      throw error;
    }
  }
  
  get(path) { return this.request('GET', path); }
  post(path, data) { return this.request('POST', path, data); }
  put(path, data) { return this.request('PUT', path, data); }
  delete(path) { return this.request('DELETE', path); }
  
  _getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }
}

export const api = new APIClient();
```

#### Step 3.2: State Management Module
```javascript
// static/js/core/state.js
export class StateManager {
  constructor() {
    this.state = {};
    this.subscribers = {};
  }
  
  subscribe(path, callback) {
    if (!this.subscribers[path]) this.subscribers[path] = [];
    this.subscribers[path].push(callback);
  }
  
  set(path, value) {
    this.state = this._setNested(this.state, path, value);
    this._notify(path, value);
  }
  
  get(path) {
    return this._getNested(this.state, path);
  }
  
  _setNested(obj, path, value) {
    const keys = path.split('.');
    let current = obj;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!current[keys[i]]) current[keys[i]] = {};
      current = current[keys[i]];
    }
    current[keys[keys.length - 1]] = value;
    return obj;
  }
  
  _getNested(obj, path) {
    return path.split('.').reduce((curr, key) => curr?.[key], obj);
  }
  
  _notify(path, value) {
    if (this.subscribers[path]) {
      this.subscribers[path].forEach(cb => cb(value));
    }
  }
}

export const state = new StateManager();
```

#### Step 3.3: Component Module Pattern
```javascript
// static/js/components/trading-terminal.js
export class TradingTerminal {
  constructor(container) {
    this.container = container;
    this.state = {
      loading: false,
      order: null,
      error: null,
    };
    this.init();
  }
  
  async init() {
    this.render();
    this.attachEventListeners();
    await this.loadBrokerAccount();
  }
  
  attachEventListeners() {
    this.container.addEventListener('click', (e) => {
      if (e.target.matches('[data-action="place-order"]')) {
        this.placeOrder();
      }
    });
  }
  
  async placeOrder() {
    this.setState({ loading: true, error: null });
    try {
      const order = await api.post('/orders/', this.getFormData());
      this.setState({ order, loading: false });
    } catch (error) {
      this.setState({ error: error.message, loading: false });
    }
  }
  
  setState(updates) {
    this.state = { ...this.state, ...updates };
    this.render();
  }
  
  render() {
    // Render UI based on state
  }
}
```

### Phase 4: Integration & Testing (5-10 hours)
- [ ] Verify all pages load and display correctly
- [ ] Test responsive breakpoints (320px, 768px, 1024px)
- [ ] Test keyboard navigation
- [ ] Test WebSocket updates in real-time
- [ ] Test error states
- [ ] Performance audit (Lighthouse)

---

## VALIDATION CRITERIA

After refactoring, run:

```bash
# Template validation
python scripts/validate_templates.py

# Frontend structure validation
python scripts/validate_frontend_structure.py

# HTML validation
npx html-validate templates/

# CSS linting
npx stylelint static/css/

# JavaScript linting
npx eslint static/js/

# Accessibility check
npx axe-core static/

# Performance
lighthouse https://algobot.dpdns.org --output=html --output-path=./report.html

# Security headers
npm audit  # if using npm dependencies
```

---

## SUCCESS CRITERIA

- [ ] All HTML is semantic and accessible
- [ ] CSS is modular and maintainable
- [ ] JavaScript is organized and tested
- [ ] All UI states are properly handled (loading, error, success)
- [ ] Real-time updates work via WebSocket
- [ ] Responsive design works on all breakpoints
- [ ] Keyboard navigation works throughout
- [ ] No hardcoded data in UI
- [ ] All API calls properly error-handled
- [ ] Lighthouse score > 80 on all metrics

---

## TEAM ASSIGNMENTS

**Frontend Engineer 1**: CSS Refactoring (Phase 1)  
**Frontend Engineer 2**: HTML Refactoring (Phase 2)  
**Frontend Engineer 3**: JavaScript Refactoring (Phase 3)  
**QA Engineer**: Integration & Testing (Phase 4)

**Total Estimated Time**: 50-65 hours  
**Recommended Timeline**: 2-3 weeks with 2-3 engineers

---

## KEY RESOURCES

- [MDN - Semantic HTML](https://developer.mozilla.org/en-US/docs/Glossary/Semantic_HTML)
- [A11y Project](https://www.a11yproject.com/)
- [CSS Tricks](https://css-tricks.com/)
- [JavaScript Design Patterns](https://www.patterns.dev/posts/module-pattern/)
- [Fetch API Docs](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)

---

**Next Steps**: Assign frontend engineers and start with Phase 1 (CSS) in parallel with Phase 2 (HTML).
