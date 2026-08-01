// RepoLink.tsx: a first-class link from the docs site back to the repository.
//
// Quartz ships no external-link component, and `quartz.layout.ts` is a .ts
// file so it cannot hold JSX itself. So this lives as its own .tsx and is
// copied into the framework tree by the deploy workflow's overlay step
// alongside the config and content. If you add another custom component,
// extend that step too: the build only copies what it is told to.
//
// Modelled on quartz/components/PageTitle.tsx, which is the closest thing in
// the framework to what this does.
//
// WHY IT IS AT THE TOP. The footer already carries a GitHub link, and nobody
// arriving from a search result scrolls to a footer to find out what the thing
// they are reading is. The docs describe an engine that lives somewhere else;
// the way back to it should be visible without looking.

import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"
import { classNames } from "../util/lang"

const REPO_URL = "https://github.com/Wombat164/vitai"

const RepoLink: QuartzComponent = ({ displayClass }: QuartzComponentProps) => {
  return (
    <a
      href={REPO_URL}
      class={classNames(displayClass, "repo-link")}
      target="_blank"
      rel="noopener noreferrer"
    >
      <svg
        class="repo-link-mark"
        viewBox="0 0 16 16"
        width="16"
        height="16"
        aria-hidden="true"
        fill="currentColor"
      >
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
      <span>vitai on GitHub</span>
    </a>
  )
}

RepoLink.css = `
.repo-link {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.4rem 0 0.2rem 0;
  font-family: var(--bodyFont);
  font-size: 0.9rem;
  color: var(--gray);
  text-decoration: none;
  transition: color 0.2s ease;
}

.repo-link:hover {
  color: var(--secondary);
}

/* Quartz underlines external links globally; this one reads as navigation
   rather than as a citation, so it opts out. */
.repo-link.external::after {
  content: none;
}

.repo-link-mark {
  flex: 0 0 auto;
}
`

export default (() => RepoLink) satisfies QuartzComponentConstructor
