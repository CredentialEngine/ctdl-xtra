import FirecrawlApp from '@mendable/firecrawl-js';

export const SupportedCrawlers = {
  "FireCrawler": async (url: string, apiKey: string) => {
    const app = new FirecrawlApp({ apiKey });
    const crawlResponse = await app.scrapeUrl(url, {
      formats: ['html'],
    })
    
    if (!crawlResponse.success) {
      throw new Error(`Failed to crawl url ${url} using FireCrawler.`);
    }

    return crawlResponse.html;
  },
  "OxyLabs": (url: string, apiKey: string) => {},
  "BrightData": (url: string, apiKey: string) => {},
  "SmartProxy": (url: string, apiKey: string) => {},
} 
