import * as cheerio from "cheerio";
import type { AnyNode, Element } from "domhandler";
import { fetchUrl } from "../providers/http.js";

export interface ExtractContentArgs {
  url: string | string[];
  format?: string;
}

interface ExtractedContent {
  url: string;
  title: string;
  content: string;
  byteLength: number;
  error?: string;
}

const MAX_CONTENT_BYTES = 50_000; // 50KB per URL

export async function executeExtractContent(
  args: ExtractContentArgs,
): Promise<ExtractedContent[]> {
  const urls = Array.isArray(args.url) ? args.url : [args.url];
  const format = args.format || "markdown";

  // Validate URLs
  for (const u of urls) {
    const parsed = new URL(u); // throws on invalid
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error(`Unsupported URL scheme: ${parsed.protocol} — only http and https are allowed`);
    }
  }

  const results = await Promise.all(
    urls.map((url) => extractOne(url, format)),
  );

  return results;
}

async function extractOne(url: string, format: string): Promise<ExtractedContent> {
  try {
    const html = await fetchUrl(url);
    const $ = cheerio.load(html);

    // Remove non-content elements
    $("script, style, nav, header, footer, aside, iframe, noscript, svg, form").remove();
    $("[role='navigation'], [role='banner'], [role='contentinfo']").remove();
    $(".nav, .menu, .sidebar, .footer, .header, .ad, .advertisement, .cookie-banner").remove();

    const title = $("title").text().trim() || $("h1").first().text().trim() || "";

    // Extract main content area if identifiable
    let contentEl = $("main, article, [role='main'], .content, .post-content, .entry-content, #content").first();
    if (contentEl.length === 0) {
      contentEl = $("body");
    }

    let content: string;
    if (format === "markdown") {
      content = htmlToMarkdown($, contentEl);
    } else {
      content = contentEl.text().replace(/\s+/g, " ").trim();
    }

    // Truncate
    if (Buffer.byteLength(content) > MAX_CONTENT_BYTES) {
      content = Buffer.from(content).subarray(0, MAX_CONTENT_BYTES).toString("utf-8");
      content += "\n\n[Content truncated at 50KB]";
    }

    return {
      url,
      title,
      content,
      byteLength: Buffer.byteLength(content),
    };
  } catch (err) {
    return {
      url,
      title: "",
      content: "",
      byteLength: 0,
      error: (err as Error).message,
    };
  }
}

function htmlToMarkdown($: cheerio.CheerioAPI, el: cheerio.Cheerio<AnyNode>): string {
  const lines: string[] = [];

  el.find("h1, h2, h3, h4, h5, h6, p, li, pre, blockquote, td, th").each((_i, node) => {
    const tag = (node as Element).tagName?.toLowerCase();
    const text = $(node).text().trim();
    if (!text) return;

    switch (tag) {
      case "h1":
        lines.push(`# ${text}`);
        break;
      case "h2":
        lines.push(`## ${text}`);
        break;
      case "h3":
        lines.push(`### ${text}`);
        break;
      case "h4":
      case "h5":
      case "h6":
        lines.push(`#### ${text}`);
        break;
      case "li":
        lines.push(`- ${text}`);
        break;
      case "pre":
        lines.push(`\`\`\`\n${text}\n\`\`\``);
        break;
      case "blockquote":
        lines.push(`> ${text}`);
        break;
      default:
        lines.push(text);
    }
  });

  return lines.join("\n\n");
}
