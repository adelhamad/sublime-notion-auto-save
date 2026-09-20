# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
One static HTML page with embedded CSS and JavaScript, deployed on Vercel. The plugin is a separate Python 2.6-compatible Sublime Text package.

## Users
Sublime Text users who want to move a note into a particular Notion database and close the editor tab without waiting for the network.

## Product Purpose
Explain Save to Notion and provide complete installation, configuration, and recovery instructions.

## Capabilities and Constraints
Save the entire buffer to a durable local queue before closing its tab. Upload in a worker thread. Resume pending uploads when Sublime starts. API token and database access are supplied by the user. The repository is private; downloads require GitHub access. No background upload guarantee after quitting Sublime. No Notion credentials have been supplied for a live API test.

## Brand Commitments
Follow https://adel-dev-tools.vercel.app/: warm paper surfaces, JetBrains Mono, thin rules, compact reference sections, green status accents, and blue links.

## Evidence on Hand
Plugin source and automated tests. The page's interactive editor is explicitly a demonstration, not a live Notion connection.
