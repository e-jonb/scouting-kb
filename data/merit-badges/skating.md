---
source: https://www.scouting.org/merit-badges/skating/
fetched: 2026-03-03
bsa_version: 2026.Q1
eagle_required: false
---

# Skating Merit Badge

[![](https://www.scouting.org/wp-content/uploads/2022/03/scouting-america-logo-desktop@2x-1.png)](/)

[![](https://www.scouting.org/wp-content/uploads/2026/01/a-250-scouting-america-250-color-logo@2x.webp)![](https://www.scouting.org/wp-content/uploads/2026/01/a-250-scouting-america-250-color-logo@2x.webp)](/service/)

✕

jQuery(function ($) {
const $header = $('.header-sa-nav');
const $searchBtn = $('#search-nav');
const $input = $('.nav-search-input');
const $searchContainer = $('#search-html-container');
// Add close button once
if (!$('.nav-search-close').length) {
$searchBtn.after(
'<button type="button" class="nav-search-close" aria-label="Close search">✕</button>'
);
}
const $closeBtn = $('.nav-search-close');
// OPEN
$searchBtn.on('click', function (e) {
$("#search-nav").addClass("btn-secondary");
$("#search-nav").addClass("btn-secondary-radio-border");
if (window.innerWidth <= 1190 && window.innerWidth >= 801) {
e.preventDefault();
$header.addClass('header-search-active');
$searchContainer.css('width','90%'); $input.focus();
$closeBtn
.css({
opacity: 1,
pointerEvents: 'unset'
});
}
});
// CLOSE
$closeBtn.on('click', function () {
$("#search-nav").removeClass("btn-secondary");
$("#search-nav").removeClass("btn-secondary-radio-border");
$header.removeClass('header-search-active');
$searchContainer.css('width','auto');
$input.val('').hide();
});
$("#search-nav").on("mouseenter", function(event ){
$("#search-nav").addClass("btn-search-hover");
});
$("#search-nav").on("mouseleave", function(event ){
$("#search-nav").removeClass("btn-search-hover");
});
let lastWidth = window.innerWidth;
$(window).on('resize', function () {
const currentWidth = window.innerWidth;
// Only react if breakpoint range changes
const isInRange = currentWidth <= 1190 && currentWidth >= 801;
if (isInRange) {
resetHeaderSearch();
}
lastWidth = currentWidth;
});
function resetHeaderSearch() {
const $header = $('.header-sa-nav');
$header.removeClass('header-search-active');
$('.nav-search-input')
.val('')
.hide();
$('.nav-search-close')
.css({
opacity: 0,
pointerEvents: 'none'
});
$('#top-menu-desktop')
.css({
opacity: 1,
pointerEvents: 'auto'
});
$("#search-nav").removeClass("btn-search-hover");
$("#search-nav").removeClass("btn-secondary");
$("#search-nav").removeClass("btn-secondary-radio-border");
$searchContainer.css('width','auto');
}
});
/\*
$("#search-nav").on("click", function(event ){
$("#search-nav").addClass("btn-secondary");
$("#search-nav").addClass("btn-secondary-radio-border");
$(".nav-search-input").css("visibility", "visible");
});
$("#search-nav").on("mouseenter", function(event ){
$("#search-nav").addClass("btn-search-hover");
});
$("#search-nav").on("mouseleave", function(event ){
$("#search-nav").removeClass("btn-search-hover");
});
\*/

* [Be a scout](https://beascout.scouting.org/?utm_source=scouting&utm_medium=join_header&utm_campaign=ongoing)
* [Scout shop](https://www.scoutshop.org/)
* [Give](https://give.scouting.org/a/support-military-families)
* [My.scouting](https://my.scouting.org/)

* [Be a scout](https://beascout.scouting.org/?utm_source=scouting&utm_medium=join_header&utm_campaign=ongoing)
* [Scout shop](https://www.scoutshop.org/)
* [Give](https://give.scouting.org/a/support-military-families)
* [My.scouting](https://my.scouting.org/)

* [Programs](https://www.scouting.org/programs/)
  + [Cub Scouts](https://www.scouting.org/programs/cub-scouts/)
  + [Scouts BSA](https://www.scouting.org/programs/scouts-bsa/)
  + [Venturing](https://www.scouting.org/programs/venturing/)
  + [Sea Scouts](https://seascout.org/)
  + [Exploring](https://www.exploring.org/)
* [Scouting Safely](https://www.scouting.org/health-and-safety/)
  + [Scouts First Helpline (1-844-SCOUTS1)](https://www.scouting.org/training/youth-protection/#hotlink)
  + [Guide to Safe Scouting](https://www.scouting.org/health-and-safety/gss/)
  + [Youth Protection](https://www.scouting.org/health-and-safety/youth-protection/)
  + [Incident Reporting](https://www.scouting.org/health-and-safety/gss/gss14/)
  + [Safety Moments](https://www.scouting.org/health-and-safety/safety-moments/)
  + [Annual Health & Medical Record](https://www.scouting.org/health-and-safety/ahmr/)
* [Awards](https://www.scouting.org/awards/)
  + [Awards Central](https://www.scouting.org/awards/awards-central/)
  + [Scholarships](https://www.scouting.org/awards/scholarships/)
  + [Outdoor Ethics Awards](https://www.scouting.org/awards/awards-central/outdoor-ethics-awards/)
  + [Guide to Awards & Insignia](https://www.scouting.org/resources/insignia-guide/)
* [About](https://www.scouting.org/about/)
  + [Careers](https://www.scouting.org/careers/)
  + [Find a Local Council](https://www.scouting.org/about/local-council-locator/)
  + [Scouting Newsroom](https://scoutingnewsroom.org/)
  + [Contact Us](https://www.scouting.org/about/contact-us/)
* [Training](https://www.scouting.org/training/)
  + [Youth Training](https://www.scouting.org/training/youth/)
* [Resources](https://www.scouting.org/resources/)
  + [Commissioners](https://www.scouting.org/commissioners/)
  + [Eagle Workbook](https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/eagle-scout-workbook/)
  + [Special Needs & Disabilities](https://www.scouting.org/resources/disabilities-awareness/)
  + [International Scouting](https://www.scouting.org/international/)
  + [Council Support](https://www.scouting.org/council-support/)
  + [Scouting Wire](https://scoutingwire.org/)
  + [Recruitment](https://www.scouting.org/recruitment/)
  + [Guide to Advancement](https://www.scouting.org/resources/guide-to-advancement/)
* [Outdoor Programs](https://www.scouting.org/outdoor-programs/)
* [Merit Badges](https://www.scouting.org/skills/merit-badges/)
* [High Adventure](https://www.scouting.org/national-high-adventure-bases/)
  + [High Adventure Treks](https://www.scouting.org/national-high-adventure-bases/adventure-treks/)
  + [High Adventure Base Jobs](https://www.scouting.org/national-high-adventure-bases/jobs/)
  + [Family Adventure Camp](https://www.scouting.org/national-high-adventure-bases/family-adventure-camp/)
* [Partners](https://www.scouting.org/partnerwithus/)

* [Programs](https://www.scouting.org/programs/)
  + [Cub Scouts](https://www.scouting.org/programs/cub-scouts/)
  + [Scouts BSA](https://www.scouting.org/programs/scouts-bsa/)
  + [Venturing](https://www.scouting.org/programs/venturing/)
  + [Sea Scouts](https://seascout.org/)
  + [Exploring](https://www.exploring.org/)
* [Scouting Safely](https://www.scouting.org/health-and-safety/)
  + [Scouts First Helpline (1-844-SCOUTS1)](https://www.scouting.org/training/youth-protection/#hotlink)
  + [Guide to Safe Scouting](https://www.scouting.org/health-and-safety/gss/)
  + [Youth Protection](https://www.scouting.org/health-and-safety/youth-protection/)
  + [Incident Reporting](https://www.scouting.org/health-and-safety/gss/gss14/)
  + [Safety Moments](https://www.scouting.org/health-and-safety/safety-moments/)
  + [Annual Health & Medical Record](https://www.scouting.org/health-and-safety/ahmr/)
* [Awards](https://www.scouting.org/awards/)
  + [Awards Central](https://www.scouting.org/awards/awards-central/)
  + [Scholarships](https://www.scouting.org/awards/scholarships/)
  + [Outdoor Ethics Awards](https://www.scouting.org/awards/awards-central/outdoor-ethics-awards/)
  + [Guide to Awards & Insignia](https://www.scouting.org/resources/insignia-guide/)
* [About](https://www.scouting.org/about/)
  + [Careers](https://www.scouting.org/careers/)
  + [Find a Local Council](https://www.scouting.org/about/local-council-locator/)
  + [Scouting Newsroom](https://scoutingnewsroom.org/)
  + [Contact Us](https://www.scouting.org/about/contact-us/)
* [Training](https://www.scouting.org/training/)
  + [Youth Training](https://www.scouting.org/training/youth/)
* [Resources](https://www.scouting.org/resources/)
  + [Commissioners](https://www.scouting.org/commissioners/)
  + [Eagle Workbook](https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/eagle-scout-workbook/)
  + [Special Needs & Disabilities](https://www.scouting.org/resources/disabilities-awareness/)
  + [International Scouting](https://www.scouting.org/international/)
  + [Council Support](https://www.scouting.org/council-support/)
  + [Scouting Wire](https://scoutingwire.org/)
  + [Recruitment](https://www.scouting.org/recruitment/)
  + [Guide to Advancement](https://www.scouting.org/resources/guide-to-advancement/)
* [Outdoor Programs](https://www.scouting.org/outdoor-programs/)
* [Merit Badges](https://www.scouting.org/skills/merit-badges/)
* [High Adventure](https://www.scouting.org/national-high-adventure-bases/)
  + [High Adventure Treks](https://www.scouting.org/national-high-adventure-bases/adventure-treks/)
  + [High Adventure Base Jobs](https://www.scouting.org/national-high-adventure-bases/jobs/)
  + [Family Adventure Camp](https://www.scouting.org/national-high-adventure-bases/family-adventure-camp/)
* [Partners](https://www.scouting.org/partnerwithus/)

$("#main-menu-desktop nav ul > li").on("click", function(event ){
$(this).addClass("bg-radius-effect");
$("#main-menu-desktop nav ul > li > a").addClass("bg-radius-effect-after");
});
