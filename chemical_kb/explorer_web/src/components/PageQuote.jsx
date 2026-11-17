import {createContext, useContext, useEffect, useRef, useState} from 'react';
import {pickQuote} from '../page-quotes';
import {LANGUAGES} from '../page-quotes-data';
import './page-quotes.css';

const PageQuoteContext = createContext(null);

export function PageQuoteProvider({page, children}) {
  const [state, setState] = useState({page: null, quote: null});
  const lastPage = useRef(null);

  useEffect(() => {
    if (lastPage.current === page) return;
    lastPage.current = page;
    let quote = null;
    try {
      quote = pickQuote(page);
    } catch {
      quote = null;
    }
    setState({page, quote});
  }, [page]);

  return <PageQuoteContext.Provider value={state.page === page ? state.quote : null}>{children}</PageQuoteContext.Provider>;
}

export function PageQuote({className = ''}) {
  const quote = useContext(PageQuoteContext);
  if (!quote) return null;
  const foreign = quote.lang !== 'zh';
  return <div className={'page-quote' + (className ? ' ' + className : '')} aria-label="页面引文">
    <div className={'page-quote-body' + (foreign ? ' page-quote-body--stacked' : ' page-quote-body--inline')}>
      <span className="page-quote-text" lang={foreign ? quote.lang : 'zh-Hant'}>{quote.original}</span>
      {foreign && <span className="page-quote-translation" lang="zh-CN">{quote.translation}</span>}
    </div>
    <details className="page-quote-source">
      <summary>原文与出处</summary>
      <div className="page-quote-source-body">
        <span className="page-quote-credit">{quote.author}，{quote.work} · {LANGUAGES[quote.lang] || quote.lang}{foreign ? ' · 中文译句为本站自译' : ''}</span>
        <a href={quote.source} target="_blank" rel="noopener noreferrer">{quote.sourceLabel}</a>
      </div>
    </details>
  </div>;
}
