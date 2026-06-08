import Link from "next/link";
import PageHeader from "@/components/PageHeader";

const TEXT = {
  title: "\u4e2a\u4eba\u672c\u5730\u4f7f\u7528\u6307\u5357",
  description: "\u6309\u6700\u77ed\u8def\u5f84\u5b8c\u6210\u4e0a\u4f20\u8bba\u6587\u3001\u95ee\u7b54\u3001\u7efc\u8ff0\u3001\u7b14\u8bb0\u6c89\u6dc0\u548c Markdown \u5bfc\u51fa\u3002",
  workflowTitle: "\u63a8\u8350\u65e5\u5e38\u5de5\u4f5c\u6d41",
  workflowBody: "\u5148\u4e0a\u4f20\u5c11\u91cf\u8bba\u6587\u786e\u8ba4\u89e3\u6790\u6210\u529f\uff0c\u518d\u56f4\u7ed5\u5355\u7bc7\u548c\u591a\u7bc7\u8bba\u6587\u63d0\u95ee\uff0c\u6700\u540e\u628a\u53ef\u9760\u56de\u7b54\u3001\u6765\u6e90\u7247\u6bb5\u548c\u7efc\u8ff0\u8868\u6761\u76ee\u4fdd\u5b58\u5230\u7814\u7a76\u7b14\u8bb0\u3002\u8fd9\u6837\u53ef\u4ee5\u628a\u4e00\u6b21\u9605\u8bfb\u8fc7\u7a0b\u6c89\u6dc0\u6210\u53ef\u590d\u5236\u7684 Markdown \u5199\u4f5c\u7d20\u6750\u3002",
  tipPrefix: "\u63d0\u793a\uff1a",
  enter: "\u8fdb\u5165",
  limitsTitle: "\u4e2a\u4eba\u672c\u5730\u9650\u5236",
  commandsTitle: "\u5e38\u7528\u81ea\u68c0\u547d\u4ee4",
};

const STEPS = [
  {
    title: "\u7b2c 1 \u6b65\uff1a\u4e0a\u4f20\u8bba\u6587",
    href: "/papers",
    action: "\u8fdb\u5165\u8bba\u6587\u5e93\uff0c\u4e0a\u4f20 1-3 \u7bc7 PDF\uff0c\u7b49\u5f85\u72b6\u6001\u53d8\u4e3a completed\u3002",
    tip: "\u5982\u679c\u957f\u65f6\u95f4\u672a\u5b8c\u6210\uff0c\u5148\u770b\u4efb\u52a1\u961f\u5217\u548c\u9996\u9875\u672c\u5730\u72b6\u6001\u9762\u677f\u3002",
  },
  {
    title: "\u7b2c 2 \u6b65\uff1a\u5355\u8bba\u6587\u95ee\u7b54",
    href: "/papers",
    action: "\u6253\u5f00\u5355\u7bc7\u8bba\u6587\u8be6\u60c5\uff0c\u4f7f\u7528\u5e38\u7528\u95ee\u9898\u6a21\u677f\u6216\u8f93\u5165\u81ea\u5df1\u7684\u95ee\u9898\u3002",
    tip: "local embedding \u4e0b\u5efa\u8bae\u4f18\u5148\u7528\u82f1\u6587\u95ee\u9898\u95ee\u82f1\u6587\u8bba\u6587\uff1b\u4f4e\u7f6e\u4fe1\u5ea6\u56de\u7b54\u53ea\u4f5c\u7ebf\u7d22\u3002",
  },
  {
    title: "\u7b2c 3 \u6b65\uff1a\u8de8\u8bba\u6587\u95ee\u7b54",
    href: "/papers/ask",
    action: "\u56f4\u7ed5\u591a\u4e2a\u8bba\u6587\u6bd4\u8f83\u65b9\u6cd5\u3001\u5dee\u5f02\u3001\u5c40\u9650\u548c\u672a\u6765\u5de5\u4f5c\u3002",
    tip: "\u8de8\u8bba\u6587\u95ee\u7b54\u9002\u5408\u505a\u7efc\u8ff0\u524d\u7684\u5feb\u901f\u6478\u5e95\u3002",
  },
  {
    title: "\u7b2c 4 \u6b65\uff1a\u751f\u6210\u6587\u732e\u7efc\u8ff0\u8868",
    href: "/papers/review",
    action: "\u628a\u8bba\u6587\u6574\u7406\u4e3a\u7814\u7a76\u95ee\u9898\u3001\u65b9\u6cd5\u3001\u8bc1\u636e\u3001\u6307\u6807\u3001\u5c40\u9650\u548c\u672a\u6765\u5de5\u4f5c\u77e9\u9635\u3002",
    tip: "\u751f\u6210\u540e\u628a\u53ef\u7528\u6761\u76ee\u4fdd\u5b58\u4e3a\u7814\u7a76\u7b14\u8bb0\uff0c\u65b9\u4fbf\u540e\u7eed\u5199\u4f5c\u3002",
  },
  {
    title: "\u7b2c 5 \u6b65\uff1a\u6574\u7406\u5e76\u5bfc\u51fa\u7814\u7a76\u7b14\u8bb0",
    href: "/notes",
    action: "\u641c\u7d22\u3001\u8fc7\u6ee4\u3001\u6253\u6807\u7b7e\uff0c\u5e76\u628a\u5f53\u524d\u53ef\u89c1\u7b14\u8bb0\u5bfc\u51fa\u4e3a Markdown\u3002",
    tip: "\u5efa\u8bae\u6309\u8bfe\u9898\u3001\u65b9\u6cd5\u3001\u5b9e\u9a8c\u3001\u5f15\u7528\u56db\u7c7b\u6807\u7b7e\u6574\u7406\u3002",
  },
];

const LOCAL_LIMITS = [
  "\u5f53\u524d\u5b9a\u4f4d\u662f\u4e2a\u4eba\u672c\u5730\u4f7f\u7528\uff0c\u4e0d\u5efa\u8bae\u76f4\u63a5\u516c\u7f51\u66b4\u9732\u3002",
  "MiMo \u5f53\u524d\u672a\u63d0\u4f9b embedding \u63a5\u53e3\uff0c\u7cfb\u7edf\u4f7f\u7528 local embedding + hybrid lexical retrieval\u3002",
  "\u4e2d\u6587\u95ee\u9898\u95ee\u82f1\u6587\u8bba\u6587\u65f6\u53ef\u80fd\u53ec\u56de\u4e0d\u8db3\uff0c\u4f18\u5148\u4f7f\u7528\u82f1\u6587\u5173\u952e\u8bcd\u6216\u82f1\u6587\u95ee\u9898\u3002",
  "API Key \u53ea\u5e94\u5b58\u5728\u4e8e .env\uff0c\u62a5\u544a\u3001\u6587\u6863\u548c\u63d0\u4ea4\u4e2d\u90fd\u4e0d\u80fd\u51fa\u73b0\u771f\u5b9e key\u3002",
];

export default function GuidePage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader title={TEXT.title} description={TEXT.description} />

      <section className="bg-blue-50 border border-blue-100 rounded-xl p-5 mb-6">
        <h2 className="text-base font-semibold text-blue-900 mb-2">{TEXT.workflowTitle}</h2>
        <p className="text-sm text-blue-800 leading-relaxed">{TEXT.workflowBody}</p>
      </section>

      <section className="grid grid-cols-1 gap-4 mb-6">
        {STEPS.map((step) => (
          <div key={step.title} className="bg-white border border-gray-100 rounded-xl shadow-sm p-5">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-gray-900">{step.title}</h2>
                <p className="text-sm text-gray-600 mt-2 leading-relaxed">{step.action}</p>
                <p className="text-xs text-gray-500 mt-2">{TEXT.tipPrefix}{step.tip}</p>
              </div>
              <Link
                href={step.href}
                className="inline-flex shrink-0 items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                {TEXT.enter}
              </Link>
            </div>
          </div>
        ))}
      </section>

      <section className="bg-white border border-gray-100 rounded-xl shadow-sm p-5 mb-6">
        <h2 className="text-base font-semibold text-gray-900 mb-3">{TEXT.limitsTitle}</h2>
        <ul className="list-disc pl-5 text-sm text-gray-600 space-y-2">
          {LOCAL_LIMITS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="bg-gray-900 text-gray-100 rounded-xl p-5">
        <h2 className="text-base font-semibold mb-3">{TEXT.commandsTitle}</h2>
        <div className="space-y-2 text-xs font-mono">
          <div>docker compose ps</div>
          <div>docker compose exec -T backend python scripts/smoke_check.py</div>
          <div>docker compose exec -T backend python scripts/model_smoke_check.py</div>
        </div>
      </section>
    </div>
  );
}
