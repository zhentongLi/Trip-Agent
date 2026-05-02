/**
 * 预订跳转链接构建工具
 * 第一阶段：联盟跳转（无需 API 资质，零成本，验证用户意愿）
 * 第二阶段：接入 Amadeus / 携程开放平台实时价格
 */

// ── 景点票务 ──────────────────────────────────────────────────────────────────

/**
 * 大麦网景点/演出搜索跳转
 */
export function buildDamaiLink(attractionName: string): string {
  return `https://search.damai.cn/search.html?keyword=${encodeURIComponent(attractionName)}`
}

/**
 * 美团景点门票搜索跳转
 */
export function buildMeituanAttractionLink(attractionName: string, city: string): string {
  return `https://www.meituan.com/search/?q=${encodeURIComponent(`${city} ${attractionName} 门票`)}`
}

/**
 * 携程景点门票搜索跳转
 */
export function buildCtripAttractionLink(attractionName: string, city: string): string {
  return `https://you.ctrip.com/search/?keyword=${encodeURIComponent(attractionName)}&city=${encodeURIComponent(city)}`
}

// ── 酒店住宿 ──────────────────────────────────────────────────────────────────

/**
 * 携程酒店搜索跳转
 * @param hotelName 酒店名称
 * @param city 城市
 * @param checkin 入住日期 YYYY-MM-DD
 * @param checkout 退房日期 YYYY-MM-DD
 */
export function buildCtripHotelLink(
  hotelName: string,
  city: string,
  checkin: string,
  checkout: string,
): string {
  const params = new URLSearchParams({
    city,
    keyword: hotelName,
    checkin,
    checkout,
  })
  return `https://hotels.ctrip.com/hotels/list?${params.toString()}`
}

/**
 * 美团酒店搜索跳转
 */
export function buildMeituanHotelLink(
  hotelName: string,
  city: string,
  checkin: string,
  checkout: string,
): string {
  const params = new URLSearchParams({
    q: `${city} ${hotelName}`,
    checkin,
    checkout,
  })
  return `https://www.meituan.com/meishi/search/?${params.toString()}`
}

/**
 * 飞猪酒店搜索跳转（阿里系，支持花呗）
 */
export function buildFeiZhuHotelLink(
  hotelName: string,
  city: string,
  checkin: string,
  checkout: string,
): string {
  const params = new URLSearchParams({
    keyword: `${city} ${hotelName}`,
    startDate: checkin,
    endDate: checkout,
  })
  return `https://hotel.alitrip.com/search.htm?${params.toString()}`
}

// ── 统一入口（供组件使用）────────────────────────────────────────────────────

export interface AttractionLinks {
  ctrip: string
  meituan: string
  damai: string
}

export interface HotelLinks {
  ctrip: string
  meituan: string
  feizhu: string
}

/**
 * 生成景点的所有平台跳转链接
 */
export function getAttractionLinks(attractionName: string, city: string): AttractionLinks {
  return {
    ctrip: buildCtripAttractionLink(attractionName, city),
    meituan: buildMeituanAttractionLink(attractionName, city),
    damai: buildDamaiLink(attractionName),
  }
}

/**
 * 生成酒店的所有平台跳转链接
 */
export function getHotelLinks(
  hotelName: string,
  city: string,
  checkin: string,
  checkout: string,
): HotelLinks {
  return {
    ctrip: buildCtripHotelLink(hotelName, city, checkin, checkout),
    meituan: buildMeituanHotelLink(hotelName, city, checkin, checkout),
    feizhu: buildFeiZhuHotelLink(hotelName, city, checkin, checkout),
  }
}

/**
 * 在新标签页打开链接（统一入口，方便后续埋点）
 */
export function openBookingLink(url: string, source: string, itemName: string): void {
  // TODO: 接入埋点（GA / 自建统计），记录点击来源和目标
  if (import.meta.env.DEV) {
    console.info(`[booking] open | source=${source} | item=${itemName} | url=${url}`)
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}
